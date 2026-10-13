#!/usr/bin/env python3
"""
Extract patent details (claims, cited_by, etc.) from google_patents_details cassettes.
"""
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Patent
from src.logger import logger


def extract_patent_details():
    """Extract patent details from cassettes and update database."""
    cassettes_dir = project_root / "src" / "api" / "cassettes"
    db = SessionLocal()

    stats = {
        'cassettes_processed': 0,
        'patents_updated': 0,
        'claims_extracted': 0,
        'citations_extracted': 0,
    }

    try:
        logger.info("Extracting patent details from cassettes...")

        for cassette_file in cassettes_dir.glob('*.json'):
            try:
                with open(cassette_file, 'r') as f:
                    data = json.load(f)

                # Only process google_patents_details cassettes
                if data.get('request', {}).get('engine') != 'google_patents_details':
                    continue

                stats['cassettes_processed'] += 1

                # Get patent_id from request
                request_patent_id = data.get('request', {}).get('patent_id')
                if not request_patent_id:
                    continue

                # Find patent in database
                patent = db.query(Patent).filter_by(patent_id=request_patent_id).first()
                if not patent:
                    logger.debug(f"Patent not found in DB: {request_patent_id}")
                    continue

                updated = False
                response = data.get('response', {})

                # Extract claims
                if not patent.claims_excerpt:
                    claims = response.get('claims', [])
                    if claims and isinstance(claims, list) and len(claims) > 0:
                        # Take first 3 claims
                        claims_text = "\n\n".join([f"{i+1}. {claim}" for i, claim in enumerate(claims[:3])])
                        patent.claims_excerpt = claims_text
                        stats['claims_extracted'] += 1
                        updated = True
                        logger.info(f"✓ Extracted claims for {request_patent_id}")

                # Extract patent citations
                patent_citations = response.get('patent_citations', {})
                if patent_citations:
                    # Cited patents (cited by this patent)
                    cited_patents = patent_citations.get('original', [])
                    if cited_patents and not patent.cited_patents_json:
                        # Store simplified version
                        cited_data = {
                            'count': len(cited_patents),
                            'patents': [
                                {
                                    'patent_id': p.get('patent_id'),
                                    'title': p.get('title'),
                                    'assignee': p.get('assignee_original'),
                                    'publication_date': p.get('publication_date'),
                                }
                                for p in cited_patents[:10]  # Limit to 10
                            ]
                        }
                        patent.cited_patents_json = cited_data
                        stats['citations_extracted'] += 1
                        updated = True
                        logger.info(f"✓ Extracted {len(cited_patents)} cited patents for {request_patent_id}")

                # Extract similar documents (used as citing patents approximation)
                similar_docs = response.get('similar_documents', {})
                if similar_docs:
                    citing_patents = similar_docs.get('patents', [])
                    if citing_patents and not patent.citing_patents_json:
                        citing_data = {
                            'count': len(citing_patents),
                            'patents': [
                                {
                                    'patent_id': p.get('patent_id'),
                                    'title': p.get('title'),
                                    'publication_date': p.get('publication_date'),
                                }
                                for p in citing_patents[:10]  # Limit to 10
                            ]
                        }
                        patent.citing_patents_json = citing_data
                        patent.cited_by_count = len(citing_patents)
                        updated = True
                        logger.info(f"✓ Extracted {len(citing_patents)} citing patents for {request_patent_id}")

                if updated:
                    stats['patents_updated'] += 1

            except Exception as e:
                logger.error(f"Error processing {cassette_file.name}: {e}")
                continue

        db.commit()

        logger.info("\n📊 Statistics:")
        logger.info(f"   Cassettes processed: {stats['cassettes_processed']}")
        logger.info(f"   Patents updated: {stats['patents_updated']}")
        logger.info(f"   Claims extracted: {stats['claims_extracted']}")
        logger.info(f"   Citations extracted: {stats['citations_extracted']}")
        logger.info("\n✅ Patent details extraction completed")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == '__main__':
    extract_patent_details()
