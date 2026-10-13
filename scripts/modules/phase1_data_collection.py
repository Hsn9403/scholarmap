"""
Phase 1: Data Collection Module.

Collects data from all available sources:
- Scholar (publications, co-authors)
- Patents (inventions, assignees)
- Clinical Trials (co-authors as PIs → sponsors)
- Transparence Santé (co-authors → financial declarations)
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional
from src.logger import logger
from src.models import ScholarData, ScholarPublication


def _merge_scholar_data(db_data: ScholarData, api_data: ScholarData) -> ScholarData:
    """
    Merge Scholar data from database and API, preferring publications with more complete authors.

    Strategy:
    - For each publication, compare DB vs API versions
    - Keep the version with MORE authors (more complete list)
    - Merge co-authors from both sources
    - Use API data for metadata (citations, h-index, etc.) as it's more up-to-date

    Args:
        db_data: ScholarData from database (may have enriched authors from previous runs)
        api_data: ScholarData from fresh API call

    Returns:
        Merged ScholarData with best of both sources
    """
    # Use API metadata (more up-to-date)
    merged = ScholarData(
        author_id=api_data.author_id,
        name=api_data.name,
        affiliation=api_data.affiliation,
        citations_total=api_data.citations_total,
        h_index=api_data.h_index,
        publications_total=api_data.publications_total,
        top_publications=[],
        coauthors=[]
    )

    # Merge publications: for each title, keep the version with more authors
    publications_map = {}  # title_normalized -> publication

    # Add DB publications
    for pub in db_data.top_publications:
        title_norm = pub.title.strip().lower()
        publications_map[title_norm] = pub

    # Merge with API publications (prefer version with more authors)
    for api_pub in api_data.top_publications:
        title_norm = api_pub.title.strip().lower()

        if title_norm in publications_map:
            db_pub = publications_map[title_norm]
            db_authors_count = len(db_pub.authors) if db_pub.authors else 0
            api_authors_count = len(api_pub.authors) if api_pub.authors else 0

            # Keep the version with MORE authors
            if api_authors_count > db_authors_count:
                publications_map[title_norm] = api_pub
                logger.debug(f"Using API version of '{pub.title[:50]}...' ({api_authors_count} authors > {db_authors_count} in DB)")
            else:
                logger.debug(f"Keeping DB version of '{pub.title[:50]}...' ({db_authors_count} authors >= {api_authors_count} in API)")
        else:
            # New publication from API
            publications_map[title_norm] = api_pub

    merged.top_publications = list(publications_map.values())

    # Merge co-authors from both sources (use API coauthors as they have more metadata)
    merged.coauthors = api_data.coauthors

    logger.info(
        f"Merged {len(db_data.top_publications)} DB pubs + {len(api_data.top_publications)} API pubs "
        f"→ {len(merged.top_publications)} total pubs"
    )

    return merged


def collect_all_data(
    researcher_name: str,
    max_publications: int = 100,
    max_patents: int = 10,
    max_coauthors_ct: int = 30,
    max_coauthors_ts: int = 50,
    min_amount_ts: float = 0.0,
    skip_clinical_trials: bool = False,
    skip_transparence_sante: bool = False,
    skip_open_payments: bool = False,
    use_db_only: bool = False,
    scholar_id: str = None,
    openalex_id: str = None,
) -> Dict[str, Any]:
    """
    Collect data from all sources.

    Returns:
        Dictionary with all collected data:
        {
            'scholar': ScholarData,
            'patents': List[Patent],
            'clinical_trials_corporates': Dict[coauthor, Set[corporates]],
            'clinical_trials_links': Dict[coauthor, List[CorporateLink]],
            'transparence_sante_corporates': Dict[coauthor, Set[corporates]],
            'transparence_sante_declarations': Dict[coauthor, List[Declaration]],
            'open_payments_corporates': Dict[coauthor, Set[corporates]],
            'open_payments_records': Dict[coauthor, List[OpenPaymentsRecord]],
        }
    """
    data = {}

    # =========================================================================
    # VAGUE 1 (séquentiel) : OpenAlex seul
    # Patents est déplacé en Vague 2 pour tourner en parallèle avec CT/TS/OP.
    # Gain : ~8s (OpenAlex ~3s seul, puis Patents ∥ CT ∥ TS ∥ OP en parallèle).
    # =========================================================================

    def _collect_openalex():
        _t0 = time.time()
        logger.info("\n1️⃣  Collecting OpenAlex data...")
        try:
            if openalex_id and not use_db_only:
                from src.scholar.openalex_fallback import build_scholar_data_from_openalex
                from src.pathfinding.openalex_client import OpenAlexClient
                result = build_scholar_data_from_openalex(
                    researcher_name=researcher_name,
                    openalex_client=OpenAlexClient(),
                    max_publications=max_publications,
                    openalex_id=openalex_id,
                )
                if result:
                    logger.info(
                        f"✓ OpenAlex: {len(result.top_publications)} pubs, "
                        f"{len(result.coauthors)} co-authors, h-index={result.h_index}"
                    )
                else:
                    logger.error(f"❌ OpenAlex profile not found: {openalex_id}")
                return result
            else:
                from src.database.adapters import scientist_to_scholar_data
                db_scholar_data = scientist_to_scholar_data(
                    scientist_name=researcher_name,
                    use_db_only=use_db_only
                )
                if use_db_only:
                    if db_scholar_data:
                        logger.info(f"✓ DB-only: {len(db_scholar_data.top_publications)} pubs, {len(db_scholar_data.coauthors)} co-authors")
                    else:
                        logger.error(f"❌ DB-only: no data for {researcher_name}")
                    return db_scholar_data
                # OpenAlex sans ID fourni — on n'a pas Scholar, retourne None
                logger.warning("No openalex_id provided and not use_db_only — skipping OpenAlex fetch")
                return db_scholar_data
        except Exception as e:
            logger.error(f"Error collecting OpenAlex data: {e}")
            import traceback
            traceback.print_exc()
            # Remonter l'erreur à PostHog pour visibilité
            try:
                from services.error_tracking import capture_exception
                capture_exception(e, route='pipeline', phase='1_openalex_fetch', researcher=researcher_name, openalex_id=openalex_id)
            except Exception:
                pass
            return None
        finally:
            logger.info(f"⏱  OpenAlex: {time.time() - _t0:.1f}s")

    _t_vague1 = time.time()
    data['scholar'] = _collect_openalex()
    logger.info(f"⏱  Vague 1 total (OpenAlex seul): {time.time() - _t_vague1:.1f}s")

    def _collect_patents(scholar_data):
        _t0 = time.time()
        if max_patents <= 0:
            logger.info("\n2️⃣  Skipping Patents (max_patents=0)")
            return []
        logger.info("\n2️⃣  Collecting Patents data...")
        try:
            if use_db_only:
                from src.database.database import SessionLocal
                from src.database.models import Scientist, Patent as DBPatent
                from src.helpers import slug
                db = SessionLocal()
                patents = []
                try:
                    scientist = db.query(Scientist).filter(
                        (Scientist.name == researcher_name) |
                        (Scientist.normalized_name == slug(researcher_name))
                    ).first()
                    if scientist:
                        db_patents = db.query(DBPatent).join(DBPatent.inventors).filter(
                            Scientist.id == scientist.id
                        ).limit(max_patents).all()
                        for db_patent in db_patents:
                            co_inventors = [inv.name for inv in db_patent.inventors if inv.name != researcher_name]
                            patents.append({
                                'title': db_patent.title,
                                'patent_id': db_patent.patent_id,
                                'link': db_patent.link,
                                'current_assignee': db_patent.assignee,
                                'co_inventors': co_inventors
                            })
                        logger.info(f"✓ Retrieved {len(patents)} patents from DB")
                    else:
                        logger.warning(f"No patents found in DB for {researcher_name}")
                finally:
                    db.close()
                return patents
            else:
                from src.patents.client import PatentsClient
                # Extraire la spécialité depuis OpenAlex déjà fetchée — évite un
                # second appel OpenAlex interne dans fetch_patents_data pour GPT.
                specialty = ""
                if scholar_data and hasattr(scholar_data, 'topics') and scholar_data.topics:
                    specialty = ", ".join(
                        t.get("display_name", "") if isinstance(t, dict) else str(t)
                        for t in (scholar_data.topics or [])[:3]
                        if (t.get("display_name", "") if isinstance(t, dict) else t)
                    )
                patents_data = PatentsClient().fetch_patents_data(
                    researcher_name,
                    max_patents=max_patents,
                    researcher_specialty=specialty,
                )
                patents = patents_data.top_patents if patents_data else []
                logger.info(f"✓ Retrieved {len(patents)} patents from API")
                return patents
        except Exception as e:
            logger.error(f"Error collecting Patents data: {e}")
            return []
        finally:
            logger.info(f"⏱  Patents: {time.time() - _t0:.1f}s")

    # =========================================================================
    # VAGUE 2 (parallel) : Patents + Clinical Trials + Transparence Santé + OP
    # Patents rejoint la vague 2 : il n'a pas besoin de scholar_data et reçoit
    # maintenant la spécialité depuis OpenAlex (déjà fetchée) pour GPT.
    # CT/TS/OP nécessitent scholar_data — disponible depuis Vague 1.
    # =========================================================================

    def _collect_clinical_trials(scholar_data):
        _t0 = time.time()
        if skip_clinical_trials:
            logger.info("\n3️⃣  Skipping Clinical Trials")
            return {}, {}
        logger.info("\n3️⃣  Collecting Clinical Trials data...")
        try:
            from discover_corporates_from_clinical_trials import (
                discover_corporates_from_coauthors_clinical_trials
            )
            ct_corporates, ct_links, ct_skipped = discover_corporates_from_coauthors_clinical_trials(
                researcher_name,
                max_coauthors=max_coauthors_ct,
                max_studies_per_coauthor=20,
                skip_initials_only=True,
                use_db_only=use_db_only,
                scholar_data=scholar_data,
            )
            total = sum(len(c) for c in ct_corporates.values())
            logger.info(f"✓ Found {total} unique corporates from Clinical Trials")
            return ct_corporates, ct_links, ct_skipped
        except Exception as e:
            logger.error(f"Error collecting Clinical Trials data: {e}")
            return {}, {}, []
        finally:
            logger.info(f"⏱  Clinical Trials: {time.time() - _t0:.1f}s")

    def _collect_transparence_sante(scholar_data):
        _t0 = time.time()
        if skip_transparence_sante:
            logger.info("\n4️⃣  Skipping Transparence Santé")
            return {}, {}
        logger.info("\n4️⃣  Collecting Transparence Santé data...")
        try:
            from discover_corporates_from_transparence_sante import (
                discover_corporates_from_transparence_sante
            )
            ts_corporates, ts_declarations, ts_skipped = discover_corporates_from_transparence_sante(
                researcher_name,
                max_coauthors=max_coauthors_ts,
                min_amount=min_amount_ts,
                skip_initials_only=True,
                use_db_only=use_db_only,
                scholar_data=scholar_data,
            )
            total = sum(len(c) for c in ts_corporates.values())
            logger.info(f"✓ Found {total} unique corporates from Transparence Santé")
            return ts_corporates, ts_declarations, ts_skipped
        except Exception as e:
            logger.error(f"Error collecting Transparence Santé data: {e}")
            return {}, {}, []
        finally:
            logger.info(f"⏱  Transparence Santé: {time.time() - _t0:.1f}s")

    def _collect_open_payments(scholar_data):
        _t0 = time.time()
        if skip_open_payments:
            logger.info("\n5️⃣  Skipping Open Payments")
            return {}, {}, []
        logger.info("\n5️⃣  Collecting Open Payments (US Sunshine Act) data...")
        try:
            from concurrent.futures import ThreadPoolExecutor as _TPE, as_completed as _as_completed
            from types import SimpleNamespace
            from src.open_payments.client import OpenPaymentsClient

            coauthors = (scholar_data.coauthors or [])[:max_coauthors_ts]

            # Inclure le chercheur principal lui-même (liens directs type Abbvie → Savitz)
            seed = SimpleNamespace(name=researcher_name)
            names_to_scan = [seed] + list(coauthors)

            op_corporates = {}
            op_records = {}
            op_skipped = []

            def _fetch_one(coauthor):
                """
                Un thread par personne — client indépendant (session propre, thread-safe).
                Étape 1 : unified search (~0.4s) — retourne vite si non-américain.
                Étape 2 : paiements par profile_id (4 années en parallèle).
                """
                name = coauthor.name
                parts = name.strip().split()
                # Ignore les noms trop courts ou initiaux seuls (ex: "J Smith")
                if len(parts) < 2 or len(parts[0].replace(".", "")) < 2:
                    return name, None, "initials"
                try:
                    client = OpenPaymentsClient(timeout=10)
                    result = client.search_by_name(
                        first_name=" ".join(parts[:-1]),
                        last_name=parts[-1],
                        min_amount_usd=0.0,   # tout versement, quelle que soit la somme
                    )
                    return name, result if result.records else None, None
                except Exception as e:
                    return name, None, str(e)

            n_workers = min(len(names_to_scan), 30)
            with _TPE(max_workers=n_workers) as pool:
                futures = {pool.submit(_fetch_one, p): p for p in names_to_scan}
                for future in _as_completed(futures, timeout=45):
                    try:
                        name, result, err = future.result()
                        if result:
                            op_corporates[name] = result.companies_found
                            op_records[name] = result.records
                        elif err and err != "initials":
                            op_skipped.append(name)
                    except Exception as _fe:
                        logger.debug(f"[OP] future error: {_fe}")

            total = sum(len(c) for c in op_corporates.values())
            direct = researcher_name in op_corporates
            logger.info(
                f"✓ Found {total} unique corporates from Open Payments "
                f"({len(op_corporates)} person(s) with records"
                + (f", incl. researcher direct links" if direct else "")
                + f", {len(op_skipped)} skipped)"
            )
            return op_corporates, op_records, op_skipped

        except Exception as e:
            logger.error(f"Error collecting Open Payments data: {e}")
            import traceback
            traceback.print_exc()
            return {}, {}, []
        finally:
            logger.info(f"⏱  Open Payments: {time.time() - _t0:.1f}s")

    scholar_data = data['scholar']
    _t_vague2 = time.time()
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_patents = executor.submit(_collect_patents, scholar_data)
        future_ct = executor.submit(_collect_clinical_trials, scholar_data)
        future_ts = executor.submit(_collect_transparence_sante, scholar_data)
        future_op = executor.submit(_collect_open_payments, scholar_data)
        data['patents'] = future_patents.result()
        data['clinical_trials_corporates'], data['clinical_trials_links'], data['ct_skipped_coauthors'] = future_ct.result()
        data['transparence_sante_corporates'], data['transparence_sante_declarations'], data['ts_skipped_coauthors'] = future_ts.result()
        data['open_payments_corporates'], data['open_payments_records'], data['op_skipped_coauthors'] = future_op.result()
    logger.info(f"⏱  Vague 2 total (Patents ∥ CT ∥ TS ∥ OP): {time.time() - _t_vague2:.1f}s")

    # =========================================================================
    # PHASE 2.5 (sequential) : Coauthor validation (homonyme filtering)
    # =========================================================================
    # NOTE: Phase 2.5 disabled for now. Uncomment below to enable.
    # See docs/PHASE_2_5_ARCHITECTURE.md and test_phase2_5_interactive.py for details.
    #
    # _t_phase2_5 = time.time()
    # logger.info("\n2️⃣.5️⃣  Phase 2.5: Validating coauthor matches...")
    # try:
    #     from src.pathfinding.phase2_5_filter import apply_phase2_5_filtering
    #
    #     data = apply_phase2_5_filtering(data)
    # except Exception as e:
    #     logger.error(f"Phase 2.5 failed: {e}")
    #     import traceback
    #     traceback.print_exc()
    #     # Continue without filtering (fallback)
    # logger.info(f"⏱  Phase 2.5: {time.time() - _t_phase2_5:.1f}s")

    return data
