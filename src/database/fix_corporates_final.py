#!/usr/bin/env python3
"""
Final fix: Move Elvesys to corporates and clean up incorrect entries.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import Corporate, Institution, PatentCorporate, Patent
from src.database.parse_entities import normalize_name
from src.logger import logger
from sqlalchemy import text


def main():
    db = SessionLocal()

    try:
        # 1. Delete the incorrectly named corporate (ID: 3)
        wrong_corp = db.query(Corporate).get(3)
        if wrong_corp:
            logger.info(f"Deleting incorrect corporate: {wrong_corp.name}")
            # Move its patent links to the correct corporates first
            links = db.query(PatentCorporate).filter_by(corporate_id=3).all()

            for link in links:
                patent = db.query(Patent).get(link.patent_id)
                logger.info(f"  Patent {patent.patent_id}: will be relinked")

                # Check patent details to determine correct assignee
                # FR3134731A1 -> Elvesys
                # FR3158313A1 -> Inside Therapeutics
                if "FR3134731A1" in patent.patent_id:
                    # This should be Elvesys (we'll create it next)
                    db.delete(link)
                elif "FR3158313A1" in patent.patent_id:
                    # This should be Inside Therapeutics (ID: 4)
                    existing = db.query(PatentCorporate).filter_by(
                        patent_id=link.patent_id,
                        corporate_id=4
                    ).first()
                    if not existing:
                        link.corporate_id = 4
                    else:
                        db.delete(link)

            db.delete(wrong_corp)
            db.commit()

        # 2. Move Elvesys institution (ID: 16) to corporates
        elvesys_inst = db.query(Institution).get(16)
        if elvesys_inst:
            logger.info(f"Moving Elvesys institution to corporates")

            # Create Elvesys corporate
            elvesys_corp = Corporate(
                name="Elvesys",
                normalized_name=normalize_name("Elvesys"),
                notes="Microfluidics startup"
            )
            db.add(elvesys_corp)
            db.flush()
            logger.info(f"Created corporate: Elvesys (ID: {elvesys_corp.id})")

            # Link patent FR3134731A1 to Elvesys
            patent = db.query(Patent).filter(Patent.patent_id.like('%FR3134731A1%')).first()
            if patent:
                existing_link = db.query(PatentCorporate).filter_by(
                    patent_id=patent.id,
                    corporate_id=elvesys_corp.id
                ).first()

                if not existing_link:
                    link = PatentCorporate(
                        patent_id=patent.id,
                        corporate_id=elvesys_corp.id,
                        role="assignee"
                    )
                    db.add(link)
                    logger.info(f"Linked patent {patent.patent_id} to Elvesys as assignee")

            # Delete the institution
            db.delete(elvesys_inst)

        db.commit()
        logger.info("✅ Corporates fixed successfully")

        # 3. Verify final state
        print("\n=== FINAL STATE ===")
        print("Corporates:")
        for corp in db.query(Corporate).all():
            print(f"  - {corp.name}")
            patents = db.query(Patent).join(PatentCorporate).filter(
                PatentCorporate.corporate_id == corp.id
            ).all()
            for p in patents:
                print(f"    → Patent: {p.patent_id}")

    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
