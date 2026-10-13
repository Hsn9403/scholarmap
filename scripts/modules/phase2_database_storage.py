"""
Phase 2: Database Storage Module.

Stores all discovered data and connections to the database:
- Clinical Trials corporates → scientist_corporate table
- Transparence Santé corporates → scientist_corporate table
"""

import gc as _gc
import time as _time
from typing import Dict, Any
from src.logger import logger


def store_all_to_database(researcher_name: str, data: Dict[str, Any]):
    """
    Store all discovered data to database:
    - Scholar publications with complete author lists (enriched by Semantic Scholar)
    - Clinical Trials corporates and connections
    - Transparence Santé corporates and connections

    Args:
        researcher_name: Name of the main researcher
        data: Dictionary with all collected data from Phase 1
    """

    # =========================================================================
    # 0. SCHOLAR DATA (ENRICHED) → DATABASE
    # =========================================================================
    scholar_data = data.get('scholar')

    if scholar_data:
        _t = _time.time()
        logger.info("\n0️⃣  Enriching publication author names via OpenAlex (before DB storage)...")
        try:
            from src.pathfinding.openalex_client import OpenAlexClient
            from src.graph.enrich_publications_from_openalex import resolve_author_names_via_openalex
            openalex_client = OpenAlexClient()
            resolve_author_names_via_openalex(scholar_data, openalex_client)
        except Exception as e:
            logger.warning(f"OpenAlex enrichment failed (non-blocking): {e}")
        logger.info(f"⏱  Phase 2 / OpenAlex enrichment: {_time.time() - _t:.1f}s")
        _gc.collect()

        _t = _time.time()
        logger.info("\n0️⃣  Storing Scholar publications with complete author lists to database...")
        try:
            from src.database.store_publications_data import store_publications_data
            stats = store_publications_data(scholar_data)
            logger.info(
                f"✓ Stored {stats['publications_added']} new publications, "
                f"{stats['publications_updated']} updated, "
                f"{stats['author_links_added']} new author links"
            )
        except Exception as e:
            logger.error(f"Error storing Scholar data: {e}")
            import traceback
            traceback.print_exc()
        logger.info(f"⏱  Phase 2 / Scholar DB storage: {_time.time() - _t:.1f}s")
    else:
        logger.info("\n0️⃣  No Scholar data to store")

    # =========================================================================
    # 0b. PATENTS → DATABASE
    # =========================================================================
    patents_list = data.get('patents') or []

    if patents_list:
        _t = _time.time()
        logger.info(f"\n0b️⃣  Storing {len(patents_list)} patent(s) to database...")
        try:
            from src.database.database import SessionLocal
            from src.database.models import Scientist, Patent as DBPatent
            from src.helpers import slug
            from src.database.deduplication import find_or_create_scientist

            db = SessionLocal()
            try:
                # Find the seed researcher
                scientist = db.query(Scientist).filter(
                    Scientist.normalized_name == slug(researcher_name)
                ).first()
                if not scientist:
                    # Try partial match
                    scientist = db.query(Scientist).filter(
                        Scientist.name.ilike(f'%{researcher_name}%')
                    ).first()

                # Clear existing patent links before storing fresh results.
                # This removes stale links (e.g. from an old incorrect query) without
                # deleting the patent records themselves (other inventors keep their links).
                if scientist and scientist.patents:
                    stale_count = len(scientist.patents)
                    scientist.patents.clear()
                    db.flush()
                    logger.info(f"  Cleared {stale_count} stale patent link(s) for {researcher_name}")

                patents_added = 0
                for pt in patents_list:
                    patent_id = getattr(pt, 'patent_id', None) or slug(getattr(pt, 'title', ''))
                    if not patent_id:
                        continue

                    # Upsert by patent_id
                    claims_list = getattr(pt, 'claims_top3', None) or []
                    claims_excerpt = "\n\n".join(claims_list) if claims_list else None

                    # Check by patent_id first, then by normalized_title as fallback
                    # (prevents UniqueViolation when patent_id format differs between runs)
                    normalized_title = slug(getattr(pt, 'title', '') or '')
                    existing = (
                        db.query(DBPatent).filter_by(patent_id=patent_id).first()
                        or db.query(DBPatent).filter_by(normalized_title=normalized_title).first()
                    )
                    if not existing:
                        db_patent = DBPatent(
                            patent_id=patent_id,
                            title=getattr(pt, 'title', '') or '',
                            normalized_title=normalized_title,
                            link=getattr(pt, 'link', None),
                            assignee=getattr(pt, 'current_assignee', None),
                            publication_date=getattr(pt, 'publication_date', None),
                            filing_date=getattr(pt, 'filing_date', None),
                            priority_date=getattr(pt, 'priority_date', None),
                            cited_by_count=getattr(pt, 'cited_by', None),
                            claims_excerpt=claims_excerpt,
                            cited_patents_json=getattr(pt, 'cited_patents', None),
                            citing_patents_json=getattr(pt, 'citing_patents', None),
                            inventors_json=getattr(pt, 'inventors', None),
                        )
                        db.add(db_patent)
                        db.flush()
                        existing = db_patent
                        patents_added += 1
                    else:
                        # Always update enriched fields (claims, citations, inventors)
                        # so re-runs refresh stale data
                        if claims_excerpt:
                            existing.claims_excerpt = claims_excerpt
                        if getattr(pt, 'cited_patents', None):
                            existing.cited_patents_json = pt.cited_patents
                        if getattr(pt, 'citing_patents', None):
                            existing.citing_patents_json = pt.citing_patents
                        if getattr(pt, 'inventors', None):
                            existing.inventors_json = pt.inventors

                    # Link to seed researcher if not already linked
                    if scientist and scientist not in existing.inventors:
                        existing.inventors.append(scientist)

                    # Link all co-inventors (create Scientist records if needed)
                    co_inventor_names = getattr(pt, 'inventors', None) or []
                    for inv_name in co_inventor_names:
                        if not inv_name or slug(inv_name) == slug(researcher_name):
                            continue
                        try:
                            inv_scientist, _ = find_or_create_scientist(db, name=inv_name)
                            if inv_scientist not in existing.inventors:
                                existing.inventors.append(inv_scientist)
                        except Exception as inv_e:
                            logger.warning(f"    Could not link co-inventor '{inv_name}': {inv_e}")

                db.commit()
                logger.info(f"✓ Stored {patents_added} new patent(s), linked to {researcher_name}")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error storing patents: {e}")
            import traceback
            traceback.print_exc()
        logger.info(f"⏱  Phase 2 / Patents DB storage: {_time.time() - _t:.1f}s")
    else:
        logger.info("\n0b️⃣  No patents to store")

    # =========================================================================
    # 1. CLINICAL TRIALS → DATABASE
    # =========================================================================
    ct_corporates = data.get('clinical_trials_corporates', {})
    ct_links = data.get('clinical_trials_links', {})

    if ct_corporates:
        _t = _time.time()
        logger.info("\n1️⃣  Storing Clinical Trials corporates to database...")

        try:
            from discover_corporates_from_clinical_trials import (
                add_clinical_trials_corporates_to_database
            )

            total_added = 0
            for coauthor, corporates in ct_corporates.items():
                logger.info(f"  Processing {coauthor}: {len(corporates)} corporate(s)")

                added = add_clinical_trials_corporates_to_database(
                    coauthor,
                    corporates,
                    ct_links.get(coauthor, [])
                )
                total_added += added

            logger.info(f"✓ Added {total_added} Clinical Trials link(s) to database")

        except Exception as e:
            logger.error(f"Error storing Clinical Trials data: {e}")
        logger.info(f"⏱  Phase 2 / CT DB storage: {_time.time() - _t:.1f}s")
    else:
        logger.info("\n1️⃣  No Clinical Trials corporates to store")

    # =========================================================================
    # 2. TRANSPARENCE SANTÉ → DATABASE
    # =========================================================================
    ts_corporates = data.get('transparence_sante_corporates', {})
    ts_declarations = data.get('transparence_sante_declarations', {})

    if ts_corporates:
        _t = _time.time()
        logger.info("\n2️⃣  Storing Transparence Santé corporates to database...")

        try:
            from discover_corporates_from_transparence_sante import (
                add_transparence_sante_to_database
            )

            # Loop per-person (like CT) so an error on one co-author doesn't
            # prevent storing the seed researcher (added last in the dict).
            total_added = 0
            for person_name, companies in ts_corporates.items():
                logger.info(f"  Processing {person_name}: {len(companies)} company(ies)")
                try:
                    added = add_transparence_sante_to_database(
                        researcher_name,
                        {person_name: companies},
                        {person_name: ts_declarations.get(person_name, [])}
                    )
                    total_added += added
                except Exception as person_err:
                    logger.error(f"  Error storing TS data for {person_name}: {person_err}")

            logger.info(f"✓ Stored Transparence Santé data to database ({total_added} new links)")

        except Exception as e:
            logger.error(f"Error storing Transparence Santé data: {e}")
        logger.info(f"⏱  Phase 2 / TS DB storage: {_time.time() - _t:.1f}s")
    else:
        logger.info("\n2️⃣  No Transparence Santé corporates to store")

    # =========================================================================
    # 3. OPEN PAYMENTS (US Sunshine Act) → DATABASE
    # =========================================================================
    op_corporates = data.get('open_payments_corporates', {})
    op_records = data.get('open_payments_records', {})

    if op_corporates:
        _t = _time.time()
        logger.info("\n3️⃣  Storing Open Payments corporates to database...")
        try:
            from discover_corporates_from_open_payments import (
                add_open_payments_to_database
            )
            total_added = add_open_payments_to_database(
                researcher_name,
                op_corporates,
                op_records,
            )
            logger.info(f"✓ Stored Open Payments data to database ({total_added} new links)")
        except Exception as e:
            logger.error(f"Error storing Open Payments data: {e}")
            import traceback
            traceback.print_exc()
        logger.info(f"⏱  Phase 2 / OP DB storage: {_time.time() - _t:.1f}s")
    else:
        logger.info("\n3️⃣  No Open Payments corporates to store")

    logger.info("\n✓ Database storage complete")
