"""Retention command shared by local scripts and the Docker maintenance service."""
import argparse
from datetime import datetime
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.vault import unseal
from app.models import Record, utcnow
from app.modules.health_profile.router import erase_document


def purge_expired(db, apply=False):
    expired = [row for row in db.scalars(select(Record).where(Record.kind == "document"))
               if datetime.fromisoformat(unseal(row.payload)["expires_at"]) <= utcnow()]
    if apply:
        for row in expired:
            erase_document(db, row, "retention-task")
        db.commit()
    return len(expired)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        count = purge_expired(db, args.apply)
    print(f"{'Purged' if args.apply else 'Would purge'} {count} expired source documents and derived records")
