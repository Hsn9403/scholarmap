"""Interactive database explorer script."""

import sys
from pathlib import Path
from typing import List

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.database.database import SessionLocal
from src.database.models import (
    Scientist,
    Publication,
    Institution,
    APICall,
    PublicationAuthor,
    ScientistInstitution,
)
from src.logger import logger


def print_table(headers: List[str], rows: List[List[str]], max_width: int = 80):
    """Print a formatted table."""
    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Truncate if needed
    col_widths = [min(w, max_width // len(headers)) for w in col_widths]

    # Print header
    header_row = " | ".join(h.ljust(w)[:w] for h, w in zip(headers, col_widths))
    print(header_row)
    print("-" * len(header_row))

    # Print rows
    for row in rows:
        cells = [str(cell).ljust(w)[:w] for cell, w in zip(row, col_widths)]
        print(" | ".join(cells))


def show_overview(db):
    """Show database overview."""
    print("\n" + "=" * 60)
    print("📊 DATABASE OVERVIEW")
    print("=" * 60)

    stats = [
        ["Scientists", db.query(Scientist).count()],
        ["Publications", db.query(Publication).count()],
        ["Institutions", db.query(Institution).count()],
        ["API Calls", db.query(APICall).count()],
    ]

    print_table(["Entity", "Count"], stats)


def show_top_scientists(db, limit: int = 10):
    """Show scientists with most publications."""
    print("\n" + "=" * 60)
    print(f"👥 TOP {limit} SCIENTISTS (by publications)")
    print("=" * 60)

    results = (
        db.query(
            Scientist.name,
            Scientist.scholar_id,
            db.query(PublicationAuthor)
            .filter(PublicationAuthor.author_id == Scientist.id)
            .count()
            .label("pub_count"),
        )
        .filter(Scientist.scholar_id.isnot(None))
        .order_by(db.text("pub_count DESC"))
        .limit(limit)
        .all()
    )

    rows = [[name, scholar_id or "", str(count)] for name, scholar_id, count in results]
    print_table(["Name", "Scholar ID", "Publications"], rows)


def show_top_publications(db, limit: int = 10):
    """Show most cited publications."""
    print("\n" + "=" * 60)
    print(f"📚 TOP {limit} MOST CITED PUBLICATIONS")
    print("=" * 60)

    results = (
        db.query(Publication.title, Publication.year, Publication.cited_by)
        .filter(Publication.cited_by.isnot(None))
        .order_by(Publication.cited_by.desc())
        .limit(limit)
        .all()
    )

    rows = [
        [title[:50], str(year) if year else "N/A", str(cited)]
        for title, year, cited in results
    ]
    print_table(["Title", "Year", "Citations"], rows)


def show_institutions(db):
    """Show all institutions with scientist count."""
    print("\n" + "=" * 60)
    print("🏛️ INSTITUTIONS")
    print("=" * 60)

    results = (
        db.query(
            Institution.name,
            db.query(ScientistInstitution)
            .filter(ScientistInstitution.institution_id == Institution.id)
            .count()
            .label("scientist_count"),
        )
        .order_by(db.text("scientist_count DESC"))
        .all()
    )

    rows = [[name[:60], str(count)] for name, count in results]
    print_table(["Institution", "Scientists"], rows)


def search_scientist(db, query: str):
    """Search for scientists by name."""
    print("\n" + "=" * 60)
    print(f"🔍 SEARCH RESULTS for '{query}'")
    print("=" * 60)

    results = (
        db.query(Scientist.name, Scientist.scholar_id, Scientist.affiliation)
        .filter(Scientist.name.ilike(f"%{query}%"))
        .all()
    )

    if not results:
        print("No results found.")
        return

    rows = [
        [name, scholar_id or "N/A", (affiliation or "N/A")[:40]]
        for name, scholar_id, affiliation in results
    ]
    print_table(["Name", "Scholar ID", "Affiliation"], rows)


def show_scientist_details(db, name: str):
    """Show detailed info for a scientist."""
    scientist = db.query(Scientist).filter(Scientist.name == name).first()

    if not scientist:
        print(f"Scientist '{name}' not found.")
        return

    print("\n" + "=" * 60)
    print(f"👤 SCIENTIST DETAILS: {scientist.name}")
    print("=" * 60)
    print(f"Scholar ID: {scientist.scholar_id or 'N/A'}")
    print(f"Affiliation: {scientist.affiliation or 'N/A'}")

    # Publications
    pubs = (
        db.query(Publication)
        .join(PublicationAuthor)
        .filter(PublicationAuthor.author_id == scientist.id)
        .order_by(Publication.cited_by.desc().nullslast())
        .all()
    )

    if pubs:
        print(f"\n📚 Publications ({len(pubs)}):")
        for i, pub in enumerate(pubs[:10], 1):
            citations = f" ({pub.cited_by} citations)" if pub.cited_by else ""
            year = f" [{pub.year}]" if pub.year else ""
            print(f"  {i}. {pub.title[:70]}...{year}{citations}")

    # Institutions
    insts = (
        db.query(Institution)
        .join(ScientistInstitution)
        .filter(ScientistInstitution.scientist_id == scientist.id)
        .all()
    )

    if insts:
        print(f"\n🏛️ Affiliated Institutions ({len(insts)}):")
        for inst in insts:
            print(f"  - {inst.name}")


def interactive_mode(db):
    """Run interactive exploration mode."""
    while True:
        print("\n" + "=" * 60)
        print("🔍 INTERACTIVE DATABASE EXPLORER")
        print("=" * 60)
        print("1. Overview")
        print("2. Top Scientists")
        print("3. Top Publications")
        print("4. Institutions")
        print("5. Search Scientist")
        print("6. Scientist Details")
        print("0. Exit")
        print("=" * 60)

        choice = input("\nChoose an option: ").strip()

        if choice == "1":
            show_overview(db)
        elif choice == "2":
            show_top_scientists(db)
        elif choice == "3":
            show_top_publications(db)
        elif choice == "4":
            show_institutions(db)
        elif choice == "5":
            query = input("Enter search query: ").strip()
            if query:
                search_scientist(db, query)
        elif choice == "6":
            name = input("Enter scientist name: ").strip()
            if name:
                show_scientist_details(db, name)
        elif choice == "0":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Explore the database")
    parser.add_argument("--overview", action="store_true", help="Show overview")
    parser.add_argument(
        "--top-scientists", type=int, metavar="N", help="Show top N scientists"
    )
    parser.add_argument(
        "--top-publications", type=int, metavar="N", help="Show top N publications"
    )
    parser.add_argument("--institutions", action="store_true", help="Show institutions")
    parser.add_argument("--search", type=str, help="Search for scientist")
    parser.add_argument("--details", type=str, help="Show scientist details")
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")

    args = parser.parse_args()

    db = SessionLocal()

    try:
        if args.overview:
            show_overview(db)
        elif args.top_scientists:
            show_top_scientists(db, args.top_scientists)
        elif args.top_publications:
            show_top_publications(db, args.top_publications)
        elif args.institutions:
            show_institutions(db)
        elif args.search:
            search_scientist(db, args.search)
        elif args.details:
            show_scientist_details(db, args.details)
        elif args.interactive:
            interactive_mode(db)
        else:
            # Default: show overview and enter interactive mode
            show_overview(db)
            input("\nPress Enter to continue to interactive mode...")
            interactive_mode(db)

    finally:
        db.close()
