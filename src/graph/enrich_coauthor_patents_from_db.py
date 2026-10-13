"""
Enrich co-author corporate connections from patents already in the database.

For each person node in the graph, checks if their patents (already stored in DB)
have assignees that match known corporates. Creates scientist_corporate entries
so that enrich_graph_with_industry_connections can draw the edges.

This is a zero-cost enrichment (no API calls) — it only reads from the DB.

Two phases:
- Phase A (always runs): DB-only check for patents already stored
- Phase B (disabled by default): SerpAPI search for top co-authors' patents
"""
import os
import re
from typing import Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session, defer as _defer

from src.database.models import Scientist, Corporate, Patent, PatentCorporate, PatentInventor
from src.database.add_coauthor_industry_connections import ScientistCorporate
from src.helpers import slug, strip_accents_basic, name_variants
from src.logger import logger


def _corp_key(name: str) -> str:
    """
    Aggressive normalization for corporate name matching.

    Strips ALL non-alphanumeric characters (dots, spaces, dashes, etc.)
    so that "Renault SAS", "Renault S.A.S." and "Renault-SAS" all map to "renaultsas".
    """
    s = strip_accents_basic(name or "").lower()
    return re.sub(r"[^a-z0-9]", "", s)


def _match_assignee_to_corporate(assignee: str, corporates: list) -> Optional[Corporate]:
    """
    Match a patent assignee string against the list of known corporates.

    Three checks in order:
    1. Exact slug match (e.g. "renault_sas" == "renault_sas")
    2. Aggressive key match — strips all non-alphanumeric chars
       (e.g. "renaultsas" == "renaultsas" catches "Renault SAS" vs "Renault S.A.S.")
    3. Containment: corporate slug is contained in assignee slug (min 5 chars)
    """
    if not assignee or not assignee.strip():
        return None

    assignee_norm = slug(assignee)
    assignee_key = _corp_key(assignee)

    for corp in corporates:
        corp_norm = corp.normalized_name or ""
        if not corp_norm:
            continue

        # Check 1: Exact slug match
        if assignee_norm == corp_norm:
            return corp

        # Check 2: Aggressive key match (ignores all punctuation/spaces)
        if assignee_key and assignee_key == _corp_key(corp.name or ""):
            return corp

        # Check 3: Containment (e.g. "biocad" in "biocad_joint_stock_company")
        if len(corp_norm) >= 5 and corp_norm in assignee_norm:
            return corp

    return None


def enrich_coauthor_patents_from_db(graph: Dict[str, Any], db: Session) -> int:
    """
    Phase A: DB-only enrichment.

    For each person node in the graph, checks if their patents already stored
    in the DB have assignees matching known corporates. Creates
    scientist_corporate entries for each match found.

    These entries are then picked up by enrich_graph_with_industry_connections.

    Optimised: 3 batch queries instead of N+1 per person/patent.

    Args:
        graph: Graph dict with nodes and edges.
        db: Database session.

    Returns:
        Number of new scientist_corporate entries created.
    """
    # Load all known corporates once
    all_corporates = db.query(Corporate).all()
    if not all_corporates:
        logger.info("No corporates in DB, skipping patent co-author enrichment")
        return 0

    # Build corporate lookup by id for fast access
    corporate_by_id: dict = {c.id: c for c in all_corporates}

    logger.info(
        f"Checking co-author patents against {len(all_corporates)} known corporates..."
    )

    # Build slug → scientist lookup — colonnes nécessaires uniquement (évite ORM complet)
    class _SciRow:
        __slots__ = ('id', 'name', 'h_index')
        def __init__(self, r): self.id = r.id; self.name = r.name; self.h_index = r.h_index

    _rows = db.query(Scientist.id, Scientist.name, Scientist.h_index).filter(
        Scientist.name.isnot(None)
    ).all()
    all_scientists = [_SciRow(r) for r in _rows]
    del _rows

    scientist_by_slug: dict = {}
    for s in all_scientists:
        key = slug(s.name)
        if key not in scientist_by_slug:
            scientist_by_slug[key] = s
        else:
            existing = scientist_by_slug[key]
            if (s.h_index or 0) > (existing.h_index or 0):
                scientist_by_slug[key] = s

    # Resolve graph person nodes → DB scientist objects
    person_nodes = [n for n in graph.get("nodes", []) if n.get("type") == "person"]
    scientist_for_node: dict = {}  # node_label → Scientist
    for node in person_nodes:
        person_name = node.get("label") or node.get("id", "").replace("person:", "")
        if not person_name:
            continue
        for _variant in name_variants(person_name):
            s = scientist_by_slug.get(slug(_variant))
            if s:
                scientist_for_node[person_name] = s
                break

    if not scientist_for_node:
        return 0

    scientist_ids = list({s.id for s in scientist_for_node.values()})

    # ── Batch query 1: all patents for all matched scientists in one JOIN ──
    rows = (
        db.query(Patent, PatentInventor.scientist_id)
        .join(PatentInventor, PatentInventor.patent_id == Patent.id)
        .filter(PatentInventor.scientist_id.in_(scientist_ids))
        .all()
    )
    patent_by_id: dict = {}
    patents_by_scientist: dict = {}  # scientist_id → [Patent]
    for patent, sci_id in rows:
        patent_by_id[patent.id] = patent
        patents_by_scientist.setdefault(sci_id, []).append(patent)

    if not patent_by_id:
        logger.info("No patents found for graph persons")
        return 0

    # ── Batch query 2: all PatentCorporate links for those patents ──
    all_patent_ids = list(patent_by_id.keys())
    pc_links = (
        db.query(PatentCorporate)
        .filter(
            PatentCorporate.patent_id.in_(all_patent_ids),
            PatentCorporate.role == "assignee"
        )
        .all()
    )
    # Build map: patent_id → [corporate_id]
    pc_by_patent: dict = {}
    for pc in pc_links:
        pc_by_patent.setdefault(pc.patent_id, []).append(pc.corporate_id)

    # ── Batch query 3: existing ScientistCorporate links to avoid duplicates ──
    existing_links = db.query(ScientistCorporate).filter(
        ScientistCorporate.scientist_id.in_(scientist_ids),
        ScientistCorporate.affiliation_type == "patent_inventor"
    ).all()
    existing_set = {(lk.scientist_id, lk.corporate_id) for lk in existing_links}

    # ── In-memory matching ──
    links_created = 0
    persons_checked = 0
    new_entries = []

    for person_name, scientist in scientist_for_node.items():
        patents = patents_by_scientist.get(scientist.id, [])
        if not patents:
            continue

        persons_checked += 1
        corp_to_patents: dict = {}

        for patent in patents:
            matched_corp_ids: set = set()

            # Source 1: patents.assignee text match
            if patent.assignee and patent.assignee.strip().lower() not in (
                "individual", "individuals", ""
            ):
                corp = _match_assignee_to_corporate(patent.assignee, all_corporates)
                if corp:
                    matched_corp_ids.add(corp.id)
                    corp_to_patents.setdefault(corp, []).append(patent)

            # Source 2: PatentCorporate table (already loaded in batch)
            for corp_id in pc_by_patent.get(patent.id, []):
                if corp_id not in matched_corp_ids:
                    corp_obj = corporate_by_id.get(corp_id)
                    if corp_obj:
                        matched_corp_ids.add(corp_id)
                        corp_to_patents.setdefault(corp_obj, []).append(patent)

        for corp, matching_patents in corp_to_patents.items():
            if (scientist.id, corp.id) in existing_set:
                continue

            new_entries.append(ScientistCorporate(
                scientist_id=scientist.id,
                corporate_id=corp.id,
                affiliation_type="patent_inventor",
                notes=f"Patent inventor on {len(matching_patents)} patent(s) for {corp.name}",
                evidence_data={
                    "evidence": [
                        {
                            "patent_id": p.patent_id or "",
                            "title": p.title,
                            "assignee": p.assignee,
                            "link": p.link or (f"https://patents.google.com/patent/{p.patent_id}" if p.patent_id else "")
                        }
                        for p in matching_patents
                    ]
                }
            ))
            existing_set.add((scientist.id, corp.id))
            logger.info(
                f"  ✅ Created link: {scientist.name} → {corp.name} "
                f"({len(matching_patents)} patent(s))"
            )
            links_created += 1

    # Single commit for all new entries
    if new_entries:
        db.add_all(new_entries)
        db.commit()

    logger.info(
        f"✅ Co-author patent DB enrichment: {persons_checked} persons checked, "
        f"{links_created} new corporate links created"
    )
    return links_created


def discover_coauthor_patents_via_api(
    researcher_name: str,
    db: Session,
    max_coauthors: int = 10,
) -> int:
    """
    Phase B: SerpAPI-based patent discovery for top co-authors.

    For the top `max_coauthors` most-published co-authors of the seed researcher
    (with full names, no initials), searches Google Patents via SerpAPI and
    extracts assignees. Creates scientist_corporate entries for any match against
    known corporates.

    Cost: ~1 SerpAPI call per co-author (search only, no detail fetching).

    Args:
        researcher_name: Seed researcher name (used to rank co-authors by frequency).
        db: Database session.
        max_coauthors: Max co-authors to search (default: 10).

    Returns:
        Number of new scientist_corporate entries created.
    """
    from src.patents.client import PatentsClient
    from src.database.models import Corporate, Institution

    logger.info(f"[Phase B] Patent API discovery for top {max_coauthors} co-authors of {researcher_name}")

    # Get top co-authors by shared publication count (full names only, no initials)
    result = db.execute(text("""
        SELECT s.name, COUNT(pa.publication_id) AS pub_count
        FROM scientists s
        JOIN publications_author pa  ON pa.author_id  = s.id
        JOIN publications_author pa2 ON pa2.publication_id = pa.publication_id
        JOIN scientists seed ON seed.id = pa2.author_id
            AND LOWER(seed.name) = LOWER(:researcher_name)
        WHERE s.id != seed.id
        GROUP BY s.name
        ORDER BY pub_count DESC
        LIMIT :limit
    """), {"researcher_name": researcher_name, "limit": max_coauthors * 3})

    coauthor_names = []
    for row in result.fetchall():
        name = row[0]
        parts = name.strip().split()
        # Skip abbreviated names: single char ("H Telib") or 2-char uppercase ("CH Bruneau", "MV Salvetti")
        first = parts[0].replace(".", "").strip()
        if len(parts) >= 2 and (len(first) == 1 or (len(first) == 2 and first.isupper())):
            continue
        coauthor_names.append(name)
        if len(coauthor_names) >= max_coauthors:
            break

    if not coauthor_names:
        logger.info("[Phase B] No full-name co-authors found to search")
        return 0

    logger.info(f"[Phase B] Top {len(coauthor_names)} co-authors to search: {coauthor_names}")

    # Scientist lookup — colonnes nécessaires uniquement (évite ORM complet)
    class _SciRow:
        __slots__ = ('id', 'name', 'h_index', 'specialty_tags')
        def __init__(self, r):
            self.id = r.id
            self.name = r.name
            self.h_index = r.h_index
            self.specialty_tags = r.specialty_tags

    _rows = db.query(Scientist.id, Scientist.name, Scientist.h_index, Scientist.specialty_tags).filter(
        Scientist.name.isnot(None)
    ).all()
    scientist_by_slug: dict = {}
    for r in _rows:
        s = _SciRow(r)
        key = slug(s.name)
        if key not in scientist_by_slug or (s.h_index or 0) > (scientist_by_slug[key].h_index or 0):
            scientist_by_slug[key] = s
    del _rows

    # Load all corporates and institutions once — shared across all users/searches.
    # These are the global source of truth: if an assignee matches a known corporate
    # it's kept; if it matches a known institution it's skipped.
    all_corporates = db.query(Corporate).all()
    all_institutions = db.query(Institution).all()

    patents_client = PatentsClient()
    links_created = 0

    # ── Parallel SerpAPI fetch ──────────────────────────────────────────────
    # Resolve scientist objects first (DB lookup, fast), then fire all API
    # searches in parallel. DB writes stay sequential below.
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

    # Phase B uses raw search_by_inventor (no enrichment, ~1 call per coauthor).
    # We add middle-initial disambiguation (Rules 1/2/4) without GPT to stay fast.
    _WITHOUT_MIDDLE_THRESHOLD = 10

    def _filter_by_initial(results: list, first_last: str, initial: str) -> list:
        """
        Keep raw SerpAPI results that are compatible with the given middle initial.

        - Rule 2: inventor has correct initial/full-middle → keep
        - Rule 4: inventor has a DIFFERENT initial → reject
        - No middle info / no inventors → keep tentatively (no GPT in Phase B)
        """
        kept = []
        for r in results:
            inventors = PatentsClient._normalize_inventor_list(r.get("inventors"))
            if not inventors:
                kept.append(r)
                continue

            has_correct = any(
                PatentsClient._inventor_matches_middle_initial(inv, first_last, initial)
                for inv in inventors
            )
            if has_correct:
                kept.append(r)
                continue

            # Check Rule 4: any inventor with matching first/last but WRONG initial
            has_wrong_initial = False
            for inv in inventors:
                raw_parts = strip_accents_basic(str(inv)).strip().split()
                if len(raw_parts) != 3:
                    continue
                inv_first_last = f"{raw_parts[0]} {raw_parts[2]}"
                if inv_first_last.lower() != first_last.lower():
                    continue
                inv_mid = raw_parts[1].rstrip(".")
                if len(inv_mid) == 1 and inv_mid.isalpha() and inv_mid.upper() != initial:
                    has_wrong_initial = True
                    break

            if not has_wrong_initial:
                kept.append(r)  # No middle-name data → keep tentatively
        return kept

    def _fetch_for_name(name: str):
        """Return (name, scientist, organic_results) — no DB writes here.

        Avec middle initial (ex: "Gregory W. Albers"):
          1. search(name, num=30) → si ≥ 10 résultats → retourne directement
             (la spécificité de l'initiale suffit, pas de GPT)
          2. sinon → search(first_last, num=100) → pré-filtre corporate + GPT specialty

        Sans middle initial (ex: "Mayank Goyal"):
          1. search(name, num=100) → pré-filtre corporate + GPT specialty
        """
        scientist = None
        for _v in name_variants(name):
            scientist = scientist_by_slug.get(slug(_v))
            if scientist:
                if _v != name:
                    logger.debug(f"  [Phase B] {name}: matched DB scientist via variant '{_v}'")
                break
        if not scientist:
            logger.debug(f"  [Phase B] {name}: not in DB scientists, skipping")
            return name, None, []

        middle_initial = PatentsClient._extract_middle_initial(name)
        name_parts = name.strip().split()
        first_last = (
            f"{name_parts[0]} {name_parts[2]}"
            if middle_initial and len(name_parts) == 3
            else name
        )

        def _safe_search(inventor: str, num: int = 20) -> list:
            """search_by_inventor wrapper — returns [] instead of raising on no results."""
            try:
                raw = patents_client.search_by_inventor(inventor, num=num)
                return raw.get("organic_results", [])
            except Exception as e:
                if "hasn't returned any results" in str(e) or "no results" in str(e).lower():
                    return []
                raise  # re-raise unexpected errors

        def _gpt_validate(results: list, specialty: str) -> list:
            """GPT-filter: garde uniquement les brevets liés à la spécialité du coauteur.

            Parallélisé (max 20 workers). Si specialty est vide ou si GPT échoue,
            le résultat est conservé par défaut.

            Optimisation : si ≤ 2 candidats passent le filtre corporate, ils ont déjà
            survécu à 2 filtres stricts (nom + corporate DB) — le GPT n'apporte pas
            assez de valeur pour justifier sa latence (jusqu'à 12s). On les conserve
            directement.
            """
            if not specialty or not results:
                return results
            if len(results) <= 2:
                logger.debug(f"    [Phase B] GPT skipped — only {len(results)} candidate(s) after corporate filter (high confidence)")
                return results

            import openai
            _client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

            def _check(r):
                title = r.get("title", "")
                if not title:
                    return r, True  # pas de titre → conserver par défaut
                try:
                    resp = _client.chat.completions.create(
                        model="gpt-5.4-mini",
                        messages=[{
                            "role": "user",
                            "content": (
                                f"Does this patent relate to the field of {specialty}? "
                                f"Patent title: {title}. Answer yes or no."
                            ),
                        }],
                        max_completion_tokens=10,
                        temperature=0,
                    )
                    answer = resp.choices[0].message.content.strip().lower()
                    return r, answer.startswith("yes")
                except Exception as gpt_err:
                    logger.warning(
                        f"    [Phase B] GPT validation error for '{title[:40]}': {gpt_err}"
                    )
                    return r, True  # conserver en cas d'erreur GPT

            validated = []
            with ThreadPoolExecutor(max_workers=20) as _gpt_pool:
                for r, keep in _gpt_pool.map(_check, results):
                    if keep:
                        validated.append(r)
            return validated

        specialty = (scientist.specialty_tags or "").strip()

        try:
            if middle_initial:
                # Étape 1 : recherche avec le nom complet (initiale incluse), num=30
                primary = _safe_search(name, num=30)
                primary = _filter_by_initial(primary, first_last, middle_initial)
                logger.info(f"  [Phase B] {name}: primary={len(primary)} après filtre initial")

                if len(primary) >= _WITHOUT_MIDDLE_THRESHOLD:
                    # Assez de résultats spécifiques → pas de GPT nécessaire
                    all_results = primary
                else:
                    # Étape 2 : fallback prénom+nom — timeout 5s pour éviter les longues attentes
                    from concurrent.futures import ThreadPoolExecutor as _FbPool, TimeoutError as _FbTimeout
                    with _FbPool(max_workers=1) as _fb_pool:
                        _fb_fut = _fb_pool.submit(_safe_search, first_last, num=30)
                        try:
                            fallback_raw = _fb_fut.result(timeout=8)
                        except _FbTimeout:
                            logger.info(f"  [Phase B] {name}: fallback timeout (>8s), skipping")
                            fallback_raw = []
                    fallback_after_initial = _filter_by_initial(fallback_raw, first_last, middle_initial)
                    fallback_after_corp = [
                        r for r in fallback_after_initial
                        if _match_assignee_to_corporate(
                            (r.get("assignee") or "").strip(), all_corporates
                        )
                    ]
                    logger.info(
                        f"  [Phase B] {name}: fallback raw={len(fallback_raw)}"
                        f" → after_initial={len(fallback_after_initial)}"
                        f" → after_corp_filter={len(fallback_after_corp)}"
                        f" | assignees_dropped="
                        + str([
                            (r.get("assignee") or "")[:40]
                            for r in fallback_after_initial
                            if not _match_assignee_to_corporate(
                                (r.get("assignee") or "").strip(), all_corporates
                            )
                        ])
                    )
                    fallback = _gpt_validate(fallback_after_corp, specialty)

                    # Fusion primary + fallback, dédupliqués par link
                    seen_links = {r.get("link", "") for r in primary if r.get("link")}
                    all_results = list(primary)
                    for r in fallback:
                        link = r.get("link", "")
                        if link not in seen_links:
                            all_results.append(r)
                            seen_links.add(link)
            else:
                # Sans middle initial : recherche directe num=30 (filtre corporate appliqué après)
                results = _safe_search(name, num=30)
                # Pré-filtre : ne garder que ceux dont l'assignee matche un Corporate connu
                results = [
                    r for r in results
                    if _match_assignee_to_corporate(
                        (r.get("assignee") or "").strip(), all_corporates
                    )
                ]
                # Validation GPT par spécialité
                all_results = _gpt_validate(results, specialty)

        except Exception as e:
            logger.warning(f"  [Phase B] {name}: patent search failed: {e}")
            return name, scientist, []

        organic = [
            {
                "assignee": r.get("assignee", "").strip(),
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "publication_number": r.get("publication_number", ""),
            }
            for r in all_results
            if r.get("assignee", "").strip()
        ]
        logger.info(f"  [Phase B] {name}: {len(organic)} patent(s) found")
        return name, scientist, organic

    with ThreadPoolExecutor(max_workers=10) as _pool:
        _futures = {_pool.submit(_fetch_for_name, n): n for n in coauthor_names}
        fetch_results = [f.result() for f in _as_completed(_futures)]

    # ── Collect corporates and link data ──────────────────────────────────────
    # Phase B only creates LINKS to existing corporates — never new Corporate records.
    # New corporates enter the DB exclusively via reliable signals (OpenPayments,
    # Transparence Santé, ClinicalTrials), shared across all users.
    assignee_to_corp: dict = {}  # Maps assignee string → Corporate object
    link_queue: list = []  # (scientist_id, assignee, patent_result)

    for name, scientist, organic in fetch_results:
        if not scientist or not organic:
            continue

        seen_assignees: set = set()
        logger.info(f"  [Phase B] {name}: processing {len(organic)} patent assignee(s)")
        for result in organic:
            assignee = (result.get("assignee") or "").strip()
            if not assignee or assignee.lower() in ("individual", "individuals", ""):
                continue
            if assignee in seen_assignees:
                continue
            seen_assignees.add(assignee)

            # Institution check first (DB-based, shared across all users)
            if _match_assignee_to_corporate(assignee, all_institutions):
                logger.info(f"    ⊘ '{assignee}' — matched as institution, skipping")
                continue

            # Corporate check (DB-based, shared across all users)
            if assignee not in assignee_to_corp:
                corp = _match_assignee_to_corporate(assignee, all_corporates)
                if not corp:
                    logger.info(f"    ⊘ '{assignee}' — not in known corporates DB, skipping")
                    continue
                assignee_to_corp[assignee] = corp

            # Queue link creation (deferred until corporates are flushed)
            link_queue.append((scientist.id, assignee, result))

    # Now create all links with valid corporate_ids
    new_links = []
    for scientist_id, assignee, result in link_queue:
        corp = assignee_to_corp[assignee]

        # Check if link already exists
        existing = db.query(ScientistCorporate).filter_by(
            scientist_id=scientist_id,
            corporate_id=corp.id,
            affiliation_type="patent_inventor"
        ).first()

        if existing:
            logger.info(f"    → Link already exists: → {corp.name}")
            continue

        # Construct patent URL
        patent_url = result.get("link", "").strip()
        if not patent_url:
            pub = result.get("publication_number") or result.get("patent_id")
            if pub:
                patent_url = f"https://patents.google.com/patent/{pub}/en"

        patent_id = result.get("patent_id") or result.get("publication_number") or ""

        sci_corp = ScientistCorporate(
            scientist_id=scientist_id,
            corporate_id=corp.id,
            affiliation_type="patent_inventor",
            notes=f"Patent inventor (API search): {result.get('title', '')[:80]}",
            evidence_data={
                "evidence": [{
                    "patent_id": patent_id,
                    "title": result.get("title", ""),
                    "assignee": assignee,
                    "link": patent_url
                }]
            }
        )
        new_links.append(sci_corp)
        links_created += 1
        logger.info(f"    ✅ Queued link: → {corp.name} (via '{result.get('title', '')[:50]}')")

    # Add and commit all links
    if new_links:
        db.add_all(new_links)

    if new_links:
        db.commit()

    logger.info(f"✅ [Phase B] {links_created} new corporate links created from API patent search")
    return links_created
