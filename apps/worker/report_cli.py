"""Admin-only import; source files and their hashes are retained outside git."""
import argparse
import json
from datetime import datetime

from src.db.session import SessionLocal
from src.domain.reports import import_report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=("ads", "income"))
    p.add_argument("file")
    p.add_argument("--shop-id", type=int, required=True)
    p.add_argument("--timezone", required=True)
    p.add_argument("--observed-at", type=datetime.fromisoformat, required=True)
    a = p.parse_args()
    with SessionLocal() as session:
        print(json.dumps(import_report(session, a.shop_id, a.file, a.kind, a.timezone,
                                       a.observed_at), default=str))


if __name__ == "__main__":
    main()
