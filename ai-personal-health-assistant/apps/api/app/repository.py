import json
from importlib.resources import files
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.core.vault import seal, unseal
from app.models import Record, Consent, Audit, uid, utcnow
from health_core.body_progress.engine import build_progress, dashboard_payload, planner_context


def consent(db, user_id, purpose, required=True):
    row = db.scalar(select(Consent).where(Consent.user_id == user_id, Consent.purpose == purpose)
                    .order_by(Consent.created_at.desc(), Consent.id.desc()).limit(1))
    if required and (row is None or not row.granted):
        raise HTTPException(403, f"Consent required: {purpose}")
    return row if row and row.granted else None


def audit(db, user_id, actor, action, entity, data=None):
    db.add(Audit(subject_id=user_id, actor_id=actor, action=action, entity_id=entity, payload=seal(data or {})))


def own(db, user_id, record_id, kind=None):
    row = db.scalar(select(Record).where(Record.id == record_id, Record.user_id == user_id))
    if row is None or (kind and row.kind != kind):
        raise HTTPException(404, "Record not found")
    return row


def records(db, user_id, kind):
    return list(db.scalars(select(Record).where(Record.user_id == user_id, Record.kind == kind)
                           .order_by(Record.created_at, Record.id)))


def singleton(db, user_id, kind):
    return db.scalar(select(Record).where(Record.user_id == user_id, Record.kind == kind, Record.slot == kind))


def view(row):
    return {**unseal(row.payload), "id": row.id, "version": row.version,
            "created_at": row.created_at.isoformat(), "updated_at": row.updated_at.isoformat()}


def create(db, user_id, kind, data, *, parent_id=None, document_id=None, slot=None, record_id=None):
    row = Record(id=record_id or uid(), user_id=user_id, kind=kind, payload=seal(data),
                 parent_id=parent_id, document_id=document_id, **({"slot": slot} if slot else {}))
    db.add(row)
    db.flush()
    return row


def replace(db, row, expected_version, data, actor, reason="user_edit"):
    before = unseal(row.payload)
    result = db.execute(update(Record).where(Record.id == row.id, Record.version == expected_version)
                        .values(payload=seal(data), version=Record.version + 1, updated_at=utcnow())
                        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "Record changed. Reload before saving")
    audit(db, row.user_id, actor, row.kind + ".updated", row.id,
          {"before": before, "after": data, "reason": reason, "previous_version": expected_version})
    db.flush()
    db.refresh(row)
    return row


def save_singleton(db, user_id, kind, data, version):
    row = singleton(db, user_id, kind)
    if row:
        return replace(db, row, version, data, user_id)
    if version != 0:
        raise HTTPException(409, "Record changed. Reload before saving")
    try:
        row = create(db, user_id, kind, data, slot=kind)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Record changed. Reload before saving")
    audit(db, user_id, user_id, kind + ".created", row.id, {"after": data})
    return row


def progress(db, user_id):
    consent(db, user_id, "health_data_processing")
    profile = singleton(db, user_id, "profile")
    config = json.loads(files("health_core").joinpath("configs/progress_phase4.json").read_text(encoding="utf-8"))
    config["report_timezone"] = unseal(profile.payload)["timezone"] if profile else "Asia/Bangkok"
    rows = records(db, user_id, "observation")
    if len(rows) > 10000:
        raise HTTPException(409, "Progress limit reached; export the full history for offline analysis")
    observations = [unseal(row.payload) for row in rows]
    from datetime import datetime
    # Server-generated ingestion timestamps can advance by microseconds to order
    # corrections across workers. A current snapshot includes all committed input.
    config["as_of"] = max([utcnow(), *(datetime.fromisoformat(row["recorded_at"]) for row in observations)]).isoformat()
    return build_progress(observations, config)
