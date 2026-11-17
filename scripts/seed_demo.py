"""Seed or clear the synthetic demo dataset.

Demo rows are labelled ``source='demo'`` and are excluded when the dashboard's
"Show live only" toggle is used.  They exist so a fresh clone has an
explorable UI before the first real upload.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.anpr.db import Database  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed or clear AutoGuard demo data.")
    parser.add_argument("--days", type=int, default=21, help="Number of days to spread demo rows over.")
    parser.add_argument("--clear", action="store_true", help="Delete all demo analyses instead of seeding.")
    parser.add_argument("--db", type=Path, default=None, help="Optional path to the SQLite database.")
    args = parser.parse_args()

    db = Database(args.db)
    if args.clear:
        removed = db.clear_demo()
        print(f"Removed {removed} demo analyses.")
        return 0
    existing = db.summary(days=365)["demo_analyses"]
    if existing:
        print(f"{existing} demo analyses already exist. Run with --clear first if you want a fresh set.")
        return 0
    count = db.seed_demo(days=args.days)
    summary = db.summary(days=30)
    print(f"Seeded {count} demo analyses ({summary['total_plates']} plate rows).")
    print(f"Review queue: {summary['review']} · recovered: {summary['recovered']} · retries: {summary['retries']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
