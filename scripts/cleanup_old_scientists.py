"""
Cleanup script: keep only the N most recent scientists, delete the rest.
Preserves analytics tables entirely.

Usage:
    python3 scripts/cleanup_old_scientists.py --dry-run   # show what would happen
    python3 scripts/cleanup_old_scientists.py --run       # execute (makes a pg_dump backup first)
"""
import os
import sys
import argparse
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

import psycopg2

KEEP_N = 20
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_conn():
    return psycopg2.connect(DATABASE_URL)


def list_scientists(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, created_at FROM scientists ORDER BY created_at DESC")
        return cur.fetchall()


def do_backup():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backup_before_cleanup_{ts}.sql"
    print(f"  → pg_dump backup: {backup_file}")
    result = subprocess.run(
        ["pg_dump", DATABASE_URL, "-f", backup_file],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  ⚠ pg_dump failed: {result.stderr}")
        print("  Aborting for safety.")
        sys.exit(1)
    print(f"  ✓ Backup saved to {backup_file}")
    return backup_file


def delete_scientists(conn, ids_to_delete):
    if not ids_to_delete:
        print("Nothing to delete.")
        return
    with conn.cursor() as cur:
        placeholders = ",".join(["%s"] * len(ids_to_delete))
        # Junction tables first
        cur.execute(f"DELETE FROM scientist_coauthors WHERE scientist_id IN ({placeholders})", ids_to_delete)
        cur.execute(f"DELETE FROM scientist_publications WHERE scientist_id IN ({placeholders})", ids_to_delete)
        cur.execute(f"DELETE FROM scientist_patents WHERE scientist_id IN ({placeholders})", ids_to_delete)
        cur.execute(f"DELETE FROM scientist_corporates WHERE scientist_id IN ({placeholders})", ids_to_delete)
        cur.execute(f"DELETE FROM scientist_clinical_trials WHERE scientist_id IN ({placeholders})", ids_to_delete)
        # Then scientists
        cur.execute(f"DELETE FROM scientists WHERE id IN ({placeholders})", ids_to_delete)
    conn.commit()
    print(f"  ✓ Deleted {len(ids_to_delete)} scientists and their related data.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without doing anything")
    parser.add_argument("--run", action="store_true", help="Execute the cleanup")
    args = parser.parse_args()

    if not args.dry_run and not args.run:
        parser.print_help()
        sys.exit(0)

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    conn = get_conn()
    scientists = list_scientists(conn)
    total = len(scientists)

    keep = scientists[:KEEP_N]
    delete = scientists[KEEP_N:]

    print(f"\nTotal scientists in DB: {total}")
    print(f"Will KEEP: {len(keep)}")
    print(f"Will DELETE: {len(delete)}")
    print()

    print(f"{'='*55}")
    print(f"  TOP {KEEP_N} — CONSERVÉS (du plus récent au plus ancien)")
    print(f"{'='*55}")
    for i, (sid, name, created_at) in enumerate(keep):
        print(f"  {i+1:2}. [{str(created_at)[:16]}]  {name}")

    if delete:
        print()
        print(f"{'='*55}")
        print(f"  SUPPRIMÉS ({len(delete)} entrées)")
        print(f"{'='*55}")
        for sid, name, created_at in delete:
            print(f"  -  [{str(created_at)[:16]}]  {name}")

    if args.dry_run:
        print("\n[DRY-RUN] Aucune modification effectuée.")
        print("Relancez avec --run pour exécuter.")
        conn.close()
        return

    if args.run:
        print("\n⚠  ATTENTION: Cette opération est irréversible (sauf backup).")
        confirm = input("Confirmer la suppression ? (tapez 'OUI') : ")
        if confirm.strip() != "OUI":
            print("Annulé.")
            conn.close()
            return

        print("\nCréation du backup...")
        do_backup()

        ids_to_delete = [row[0] for row in delete]
        print(f"\nSuppression de {len(ids_to_delete)} scientists...")
        delete_scientists(conn, ids_to_delete)
        print("✓ Nettoyage terminé.")

    conn.close()


if __name__ == "__main__":
    main()
