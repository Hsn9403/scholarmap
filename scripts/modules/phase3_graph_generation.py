"""
Phase 3: Graph Generation Module.

Generates the interactive HTML graph with all data:
- Publications and co-authors from Scholar
- Patents and inventors
- Industry connections from database (including new Clinical Trials & Transparence Santé)
"""

from typing import Optional, Any
from pathlib import Path
from src.logger import logger
from src.progress import report
from src.helpers import slug


def generate_complete_graph(
    researcher_name: str,
    scholar_data: Optional[Any],
    patents_data: Optional[list],
    enrich_persons: bool = True,
    discover_coauthor_patents_api: bool = True
) -> str:
    """
    Generate complete interactive graph.

    Args:
        researcher_name: Name of the researcher
        scholar_data: Scholar data object
        patents_data: List of patents
        enrich_persons: Whether to enrich person nodes
        discover_coauthor_patents_api: Phase B — search SerpAPI for co-author patents.
            DISABLED BY DEFAULT (costs ~1 SerpAPI call per co-author).
            When enabled, searches top 10 most-published co-authors only.

    Returns:
        Path to generated HTML file
    """
    from src.graph.builder import build_graph_data
    from src.graph.visualizer import render_graph_html
    from src.graph.enrich_with_industry import enrich_graph_with_industry_connections
    from src.graph.enrich_persons_from_db import enrich_persons_from_db
    from src.graph.enrich_patents_from_db import enrich_patents_from_db
    from src.graph.enrich_coauthor_patents_from_db import enrich_coauthor_patents_from_db

    import gc as _gc
    import time as _time
    import tracemalloc as _tm

    if not _tm.is_tracing():
        _tm.start()

    def _p3_snap(label: str):
        cur, peak = _tm.get_traced_memory()
        logger.info(f"[RAM/P3] {label} — current: {cur/1024/1024:.1f} MB | peak: {peak/1024/1024:.1f} MB")

    report("graph_base")
    logger.info("\n1️⃣  Building base graph...")
    _t = _time.time()

    # Detect whether the seed researcher was sourced from OpenAlex
    _is_openalex_source = bool(
        scholar_data
        and getattr(scholar_data, "author_id", None)
        and "openalex.org" in scholar_data.author_id
    )

    # Build base graph from Scholar + Patents
    from src.models import PatentsData

    # Convert patents list to PatentsData if needed
    if patents_data and isinstance(patents_data, list):
        patents_obj = PatentsData(top_patents=patents_data, patents_total=len(patents_data))
    elif patents_data:
        patents_obj = patents_data
    else:
        patents_obj = PatentsData(top_patents=[], patents_total=0)

    graph_data = build_graph_data(
        researcher_name=researcher_name,
        scholar=scholar_data,
        patents=patents_obj,
        max_patents=0,
        enrich_persons=False,
        scholar_client=None,
        max_persons_to_enrich=0
    )

    logger.info(f"⏱  Phase 3 / build_graph_data: {_time.time() - _t:.1f}s")
    logger.info(f"  Nodes: {len(graph_data['nodes'])}, Edges: {len(graph_data['edges'])}")
    _p3_snap("après build_graph_data")

    # Enrich person names from database (replace abbreviated names with full names)
    report("persons_db")
    logger.info("\n1.5️⃣  Enriching person names from database...")

    from src.database.database import SessionLocal

    # Retry loop : Clever Cloud free PostgreSQL a un ROLCONNLIMIT très bas.
    # On attend que les connexions précédentes soient libérées.
    _t = _time.time()
    db = None
    for _attempt in range(6):
        try:
            db = SessionLocal()
            db.execute(__import__('sqlalchemy').text('SELECT 1'))  # test connexion
            break
        except Exception as _conn_err:
            if db:
                try:
                    db.close()
                except Exception:
                    pass
                db = None
            logger.warning(f"DB connection attempt {_attempt+1}/6 failed: {_conn_err} — retrying in {2**_attempt}s")
            _time.sleep(2 ** _attempt)

    logger.info(f"⏱  Phase 3 / DB connection: {_time.time() - _t:.1f}s")

    if db is None:
        logger.error("Could not connect to DB after 6 attempts — skipping DB enrichment")
        db = None

    try:
        if db is None:
            raise RuntimeError("No DB connection available")

        _t = _time.time()
        graph_data = enrich_persons_from_db(graph=graph_data, db=db)
        logger.info(f"⏱  Phase 3 / enrich_persons_from_db: {_time.time() - _t:.1f}s")
        db.expire_all()
        _gc.collect()
        _p3_snap("après enrich_persons_from_db")

        # Enrich with patents from database (before OpenAlex enrichment so that
        # co-inventor person nodes are created first and then enriched with OpenAlex)
        report("patents_db")
        logger.info("\n1.6️⃣  Enriching with patents from database...")
        _t = _time.time()
        graph_data = enrich_patents_from_db(
            graph=graph_data,
            db=db,
            researcher_name=researcher_name
        )
        logger.info(f"⏱  Phase 3 / enrich_patents_from_db: {_time.time() - _t:.1f}s")
        db.expire_all()
        _gc.collect()
        _p3_snap("après enrich_patents_from_db")

        # When seed source is OpenAlex: enrich ALL person nodes (co-authors + co-inventors)
        # with OpenAlex data (h_index, openalex profile URL).
        # Must run AFTER enrich_patents_from_db so co-inventor nodes are already in the graph.
        if _is_openalex_source:
            # Health check: test OpenAlex connectivity before full enrichment
            logger.info("\n1.54️⃣  Checking OpenAlex availability...")
            try:
                from src.pathfinding.openalex_client import OpenAlexClient
                from src.exceptions import APIError
                _oa_test = OpenAlexClient()
                _oa_test.search_author("test")  # Quick test call
                logger.info("✅ OpenAlex is available")
            except APIError as e:
                if "unavailable" in str(e).lower() or "timeout" in str(e).lower():
                    logger.error("❌ OpenAlex is currently unavailable (maintenance or timeout)")
                    raise APIError("OpenAlex API is currently in maintenance. Please try again in a few minutes.") from e
                raise

            report("coauthors_openalex")
            logger.info("\n1.55️⃣  Enriching person nodes with OpenAlex data...")
            _t = _time.time()
            import threading as _threading
            from src.graph.enrich_persons_from_openalex import enrich_persons_from_openalex
            _oa_client = OpenAlexClient()
            _oa_thread = _threading.Thread(
                target=enrich_persons_from_openalex,
                kwargs={"graph": graph_data, "openalex_client": _oa_client},
                daemon=True
            )
            _oa_thread.start()
            _oa_thread.join(timeout=45)
            if _oa_thread.is_alive():
                logger.warning("OpenAlex enrichment exceeded 45s — skipping remaining nodes")
            del _oa_client
            _gc.collect()
            logger.info(f"⏱  Phase 3 / enrich_persons_from_openalex: {_time.time() - _t:.1f}s")
            _p3_snap("après enrich_persons_from_openalex")

            # Créer les nœuds institution violets depuis les affiliations OpenAlex
            report("institutions")
            logger.info("\n1.56️⃣  Ajout des nœuds institution depuis OpenAlex...")
            _t = _time.time()
            from src.graph.enrich_institutions_from_openalex import enrich_institutions_from_openalex
            graph_data = enrich_institutions_from_openalex(graph_data)
            logger.info(f"⏱  Phase 3 / enrich_institutions_from_openalex: {_time.time() - _t:.1f}s")
            _p3_snap("après enrich_institutions_from_openalex")
            _gc.collect()

        # Phase A: cross-reference co-author patents already in DB against known corporates
        report("coauthor_patents")
        logger.info("\n1.7️⃣  Checking co-author patents in DB against known corporates...")
        _t = _time.time()
        enrich_coauthor_patents_from_db(graph=graph_data, db=db)
        logger.info(f"⏱  Phase 3 / enrich_coauthor_patents_from_db (A): {_time.time() - _t:.1f}s")
        db.expire_all()
        _gc.collect()
        _p3_snap("après enrich_coauthor_patents_from_db")

        # Phase B: SerpAPI search for top co-authors' patents (disabled by default)
        # To enable: pass discover_coauthor_patents_api=True — costs ~1 SerpAPI call per co-author
        # Only runs for the top 10 most-published co-authors of the seed researcher
        if discover_coauthor_patents_api:
            logger.info("\n1.8️⃣  [Phase B] Discovering co-author patents via API (top 10)...")
            _t = _time.time()
            from src.graph.enrich_coauthor_patents_from_db import discover_coauthor_patents_via_api
            discover_coauthor_patents_via_api(
                researcher_name=researcher_name,
                db=db,
                max_coauthors=10
            )
            logger.info(f"⏱  Phase 3 / discover_coauthor_patents_via_api (B): {_time.time() - _t:.1f}s")
            db.expire_all()
            _gc.collect()
            _p3_snap("après discover_coauthor_patents (B)")

        # Enrich with industry connections from database
        report("industry")
        logger.info("\n2️⃣  Enriching with industry connections from database...")
        _t = _time.time()
        enriched_graph = enrich_graph_with_industry_connections(
            graph=graph_data,
            db=db,
            add_coauthor_nodes=True
        )
        logger.info(f"⏱  Phase 3 / enrich_graph_with_industry_connections: {_time.time() - _t:.1f}s")
        _p3_snap("après enrich_industry (avant del graph_data)")
        del graph_data  # libéré : enriched_graph le remplace
        _gc.collect()
        _p3_snap("après del graph_data")
    except RuntimeError as _no_db_err:
        logger.warning(f"DB enrichment skipped: {_no_db_err} — graph will have less enrichment")
        enriched_graph = graph_data
        del graph_data
        _gc.collect()
    finally:
        if db is not None:
            db.close()

    logger.info("✓ Graph enriched:")
    logger.info(f"  Total nodes: {len(enriched_graph['nodes'])}")
    logger.info(f"  Total edges: {len(enriched_graph['edges'])}")

    # Count corporates
    corporate_nodes = [n for n in enriched_graph['nodes'] if n.get('type') == 'corporate']
    logger.info(f"  Corporate nodes: {len(corporate_nodes)}")

    # LLM reclassification: move misclassified corporates → institution (in-memory only)
    try:
        from src.graph.reclassify_corporates_with_llm import reclassify_corporate_nodes_with_llm
        enriched_graph = reclassify_corporate_nodes_with_llm(enriched_graph)
    except Exception as _e:
        logger.warning(f"LLM reclassification skipped: {_e}")

    # Generate HTML visualization
    report("render")
    logger.info("\n3️⃣  Generating visualization...")

    output_filename = f"{slug(researcher_name).replace('-', '_')}_network.html"
    # Always save to project root (where find_graph_for_researcher looks)
    project_root = Path(__file__).parent.parent.parent
    output_path = project_root / output_filename

    _t = _time.time()
    render_graph_html(
        graph=enriched_graph,
        out_html=str(output_path)
    )
    logger.info(f"⏱  Phase 3 / render_graph_html: {_time.time() - _t:.1f}s")
    logger.info(f"✓ Graph HTML generated: {output_filename}")
    _p3_snap("après render_graph_html (avant del enriched_graph)")
    del enriched_graph  # libéré : rendu dans le fichier HTML
    _gc.collect()
    _p3_snap("après del enriched_graph")

    # Persist graph HTML to DB so it survives container restarts (Clever Cloud ephemeral FS)
    try:
        from src.database.database import SessionLocal
        from src.database.models import Scientist
        from src.helpers import slug as _slug

        with open(str(output_path), 'r', encoding='utf-8') as f:
            graph_html_content = f.read()
        _p3_snap("après lecture graph_html_content")

        _t = _time.time()
        db = SessionLocal()
        try:
            scientist = db.query(Scientist).filter_by(
                normalized_name=_slug(researcher_name)
            ).first()
            if scientist:
                scientist.graph_html = graph_html_content
                db.commit()
                logger.info(f"⏱  Phase 3 / save_graph_html_to_db: {_time.time() - _t:.1f}s")
                logger.info(f"✓ Graph HTML saved to DB for: {researcher_name}")
            else:
                logger.warning(f"Scientist not found in DB, graph HTML not persisted: {researcher_name}")
        finally:
            db.close()
        del graph_html_content  # libéré : committé en DB
        _gc.collect()
        _p3_snap("après del graph_html_content")
    except Exception as e:
        logger.warning(f"Could not save graph HTML to DB (non-blocking): {e}")

    return output_filename
