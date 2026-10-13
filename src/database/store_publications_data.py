#!/usr/bin/env python3
"""
Store publications data (from OpenAlex) to the database.

This module saves publications with their COMPLETE author lists to the database.
"""
from typing import Optional
from sqlalchemy.orm import Session

from src.models import ScholarData
from src.database.database import SessionLocal
from src.database.deduplication import find_or_create_publication, find_or_create_scientist, normalize_text
from src.database.models import PublicationAuthor
from src.logger import logger


def store_publications_data(
    scholar_data: ScholarData,
    db: Optional[Session] = None
) -> dict:
    """
    Store publications (from OpenAlex) with their complete author lists to the database.

    Optimised: pre-loads existing publications/scientists in batch queries
    instead of N+1 SELECTs per publication/author.

    Args:
        scholar_data: ScholarData object with publications and authors
        db: Database session (creates one if not provided)

    Returns:
        Dict with statistics: {
            'publications_added': int,
            'publications_updated': int,
            'scientists_added': int,
            'author_links_added': int
        }
    """
    from sqlalchemy.orm import defer as _defer
    from src.database.models import Publication, Scientist

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        stats = {
            'publications_added': 0,
            'publications_updated': 0,
            'scientists_added': 0,
            'author_links_added': 0
        }

        # ── Store main researcher (single query, unavoidable) ──────────────
        author_id = scholar_data.author_id or ""
        if author_id.startswith("https://openalex.org/"):
            short_id = author_id.split("/")[-1]
            researcher, created = find_or_create_scientist(
                db,
                name=scholar_data.name,
                scholar_url=f"https://openalex.org/{short_id}",
                affiliation=scholar_data.affiliation,
                h_index=scholar_data.h_index,
            )
        else:
            researcher, created = find_or_create_scientist(
                db,
                name=scholar_data.name,
                scholar_id=author_id if author_id else None,
                affiliation=scholar_data.affiliation,
                h_index=scholar_data.h_index,
            )
        if created:
            stats['scientists_added'] += 1

        pubs = scholar_data.top_publications
        logger.info(f"Storing {len(pubs)} publications to database...")

        if not pubs:
            db.commit()
            return stats

        # ── Batch query 1: pre-load existing publications by normalized_title ──
        all_norm_titles = [normalize_text(p.title) for p in pubs if p.title]
        existing_pubs = db.query(Publication).filter(
            Publication.normalized_title.in_(all_norm_titles)
        ).all()
        pub_by_norm_title: dict = {p.normalized_title: p for p in existing_pubs}

        # ── Batch query 2: pre-load existing scientists by normalized_name ──
        all_author_names = {researcher.normalized_name}
        for pub in pubs:
            for name in (pub.authors or []):
                if name:
                    all_author_names.add(normalize_text(name))

        existing_scientists = db.query(Scientist).options(
            _defer(Scientist.graph_html)
        ).filter(
            Scientist.normalized_name.in_(all_author_names)
        ).all()
        scientist_cache: dict = {s.normalized_name: s for s in existing_scientists}
        # Make sure the main researcher is in cache
        scientist_cache[researcher.normalized_name] = researcher

        # ── Pass 1: create missing publications and scientists ─────────────
        new_publications: list = []
        pub_objects: list = []  # (pub_data, Publication object)

        for pub in pubs:
            if not pub.title:
                continue
            norm_title = normalize_text(pub.title)
            year_int = None
            if pub.year:
                try:
                    year_int = int(pub.year)
                except (ValueError, TypeError):
                    pass

            if norm_title in pub_by_norm_title:
                publication = pub_by_norm_title[norm_title]
                stats['publications_updated'] += 1
            else:
                publication = Publication(
                    title=pub.title,
                    normalized_title=norm_title,
                    link=pub.link,
                    year=year_int,
                    cited_by=pub.cited_by,
                    source=pub.source,
                    abstract=pub.abstract,
                    authors_raw=", ".join(pub.authors) if pub.authors else None
                )
                db.add(publication)
                new_publications.append(publication)
                pub_by_norm_title[norm_title] = publication
                stats['publications_added'] += 1

            pub_objects.append((pub, publication))

        # Create missing scientists
        new_scientists: list = []
        for pub in pubs:
            for author_name in (pub.authors or []):
                if not author_name:
                    continue
                norm = normalize_text(author_name)
                if norm not in scientist_cache:
                    scientist = Scientist(
                        name=author_name,
                        normalized_name=norm
                    )
                    db.add(scientist)
                    scientist_cache[norm] = scientist
                    new_scientists.append(scientist)
                    stats['scientists_added'] += 1

        # Flush once to get IDs for new publications and scientists
        if new_publications or new_scientists:
            db.flush()

        # ── Batch query 3: pre-load existing PublicationAuthor links ──────
        all_pub_ids = [pub_obj.id for _, pub_obj in pub_objects if pub_obj.id]
        existing_pa = db.query(PublicationAuthor).filter(
            PublicationAuthor.publication_id.in_(all_pub_ids)
        ).all()
        existing_pa_set = {(pa.publication_id, pa.author_id) for pa in existing_pa}

        # ── Pass 2: create PublicationAuthor links in memory ──────────────
        new_links: list = []
        for pub_data, publication in pub_objects:
            if not pub_data.authors or not publication.id:
                continue
            for author_name in pub_data.authors:
                if not author_name:
                    continue
                norm = normalize_text(author_name)
                author = scientist_cache.get(norm)
                if not author or not author.id:
                    continue
                key = (publication.id, author.id)
                if key not in existing_pa_set:
                    new_links.append(PublicationAuthor(
                        publication_id=publication.id,
                        author_id=author.id
                    ))
                    existing_pa_set.add(key)
                    stats['author_links_added'] += 1

        if new_links:
            db.add_all(new_links)

        # Single commit for everything
        db.commit()

        # Libérer les objets ORM de l'identity map pour réduire la RAM
        # (centaines de Publication/Scientist/PublicationAuthor sur gros chercheurs)
        db.expunge_all()

        logger.info(
            f"✅ Stored Scholar data: "
            f"{stats['publications_added']} new publications, "
            f"{stats['publications_updated']} updated, "
            f"{stats['scientists_added']} new scientists, "
            f"{stats['author_links_added']} new author links"
        )

        return stats

    except Exception as e:
        logger.error(f"Error storing Scholar data to database: {e}")
        db.rollback()
        raise

    finally:
        if close_db:
            db.close()
