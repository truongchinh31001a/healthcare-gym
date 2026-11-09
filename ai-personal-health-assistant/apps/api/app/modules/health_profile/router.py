from datetime import timedelta, datetime
from io import BytesIO
import hashlib
import warnings
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select, func, update
from PIL import Image
import pypdfium2 as pdfium
from starlette.concurrency import run_in_threadpool
from app.core.config import settings
from app.core.vault import seal, unseal, vault, blob_path
from app.core.security import password_valid
from app.shared.dependencies import get_db, get_current_user, require_admin, aware
from app.models import Record, User, Consent, Audit, uid, utcnow
from app.schemas import (ConsentInput, Profile, HealthContext, MeasurementInput, Revision,
                         Transcription, ConfirmDraft, GoalInput, GoalRevision, Reauthenticate)
from app import repository as repo
from .safety import screen_goal
from health_core.body_progress.schema import FIELDS
from health_core.body_progress.engine import normalize_observation, dashboard_payload, planner_context
from health_core.body_progress.adapters import observations_from_review
from health_core.document_ai.parser import parse_lines, validate_values
from health_core.document_ai.schema import FIELDS as REPORT_FIELDS
from health_core.document_ai.review import confirm_fields
from health_core.body_progress.contracts import summary_schemas

router = APIRouter(tags=["module-01"])
PURPOSES = ("health_data_processing", "document_processing", "body_image_processing", "admin_support", "research_training")


def capabilities():
    return {"manual_measurements": True, "report_transcription_and_review": True,
            "ocr": {"enabled": False, "reason": "Real report benchmark has not passed release review"},
            "body_cv": {"enabled": False, "reason": "Uncertainty and real capture validation gates have not passed"},
            "generative_planner": {"enabled": False, "reason": "Clinical safety evaluation pending"},
            "rule_version": "wellness-goals-v1"}


@router.get("/capabilities")
def get_capabilities(user=Depends(get_current_user)):
    return capabilities()


@router.get("/me/consents")
def list_consents(user=Depends(get_current_user), db=Depends(get_db)):
    return [{"purpose": purpose, "granted": bool(repo.consent(db, user.id, purpose, False)),
             "policy_version": "module01-v1"} for purpose in PURPOSES]


@router.post("/me/consents", status_code=201)
def set_consent(body: ConsentInput, user=Depends(get_current_user), db=Depends(get_db)):
    row = Consent(user_id=user.id, purpose=body.purpose, granted=body.granted)
    db.add(row)
    db.flush()
    repo.audit(db, user.id, user.id, "consent.changed", row.id, body.model_dump())
    if body.purpose == "health_data_processing" and not body.granted:
        invalidate_goals(db, user.id, "processing_consent_revoked")
    db.commit()
    return {"id": row.id, **body.model_dump(), "policy_version": row.policy_version}


def invalidate_goals(db, user_id, reason):
    for goal in repo.records(db, user_id, "goal"):
        data = unseal(goal.payload)
        if data["status"] == "active":
            repo.replace(db, goal, goal.version, {**data, "status": "needs_rescreening"}, user_id, reason)


@router.get("/me/profile")
def get_profile(user=Depends(get_current_user), db=Depends(get_db)):
    row = repo.singleton(db, user.id, "profile")
    return repo.view(row) if row else None


@router.put("/me/profile")
def put_profile(body: Profile, user=Depends(get_current_user), db=Depends(get_db)):
    repo.consent(db, user.id, "health_data_processing")
    row = repo.save_singleton(db, user.id, "profile", body.model_dump(mode="json", exclude={"version"}), body.version)
    invalidate_goals(db, user.id, "profile_changed")
    db.commit()
    return repo.view(row)


@router.get("/me/health-context")
def get_context(user=Depends(get_current_user), db=Depends(get_db)):
    row = repo.singleton(db, user.id, "health_context")
    return repo.view(row) if row else {**HealthContext().model_dump(), "id": None}


@router.put("/me/health-context")
def put_context(body: HealthContext, user=Depends(get_current_user), db=Depends(get_db)):
    repo.consent(db, user.id, "health_data_processing")
    row = repo.save_singleton(db, user.id, "health_context", body.model_dump(exclude={"version"}), body.version)
    invalidate_goals(db, user.id, "health_context_changed")
    db.commit()
    return repo.view(row)


def validate_units(values):
    if len({value.field for value in values}) != len(values):
        raise HTTPException(422, "Each field may occur only once per session")
    for value in values:
        if value.unit.lower() not in FIELDS[value.field]["units"]:
            raise HTTPException(422, f"Unsupported unit for {value.field}")


@router.post("/me/measurement-sessions", status_code=201)
def add_session(body: MeasurementInput, user=Depends(get_current_user), db=Depends(get_db)):
    grant = repo.consent(db, user.id, "health_data_processing")
    profile = repo.singleton(db, user.id, "profile")
    if not profile:
        raise HTTPException(409, "Complete your profile first")
    validate_units(body.values)
    allowed = {"scale": {"weight_kg"}, "tape": {"height_cm", "chest_cm", "waist_cm", "hip_cm", "bicep_cm", "thigh_cm"},
               "device_report": set(REPORT_FIELDS)}[body.measurement_method]
    if any(value.field not in allowed for value in body.values):
        raise HTTPException(422, "Measurement method does not support the selected fields")
    session = repo.create(db, user.id, "measurement_session", body.model_dump(mode="json", exclude={"values"}))
    rows = []
    for value in body.values:
        data = {"observation_id": uid(), "subject_id": user.id, "measurement_session_id": session.id,
                "field": value.field, "value": value.value, "unit": value.unit, "measured_at": body.measured_at.isoformat(),
                "recorded_at": utcnow().isoformat(), "measurement_timezone": unseal(profile.payload)["timezone"],
                "source": "manual_measurement", "provenance": "observed", "measurement_method": body.measurement_method,
                "verification_status": "confirmed_by_user", "device_id": body.device_id, "device_model": body.device_model,
                "protocol_id": body.protocol_id, "model_version": None, "consent_id": grant.id,
                "synthetic": False, "quality_flags": []}
        normalize_observation(data, {"report_timezone": data["measurement_timezone"], "as_of": utcnow().isoformat()})
        rows.append(repo.view(repo.create(db, user.id, "observation", data, parent_id=session.id)))
    invalidate_goals(db, user.id, "measurements_changed")
    repo.audit(db, user.id, user.id, "measurement.created", session.id)
    db.commit()
    return {"session": repo.view(session), "observations": rows}


@router.get("/me/observations")
def observations(user=Depends(get_current_user), db=Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
    rows = list(db.scalars(select(Record).where(Record.user_id == user.id, Record.kind == "observation")
                          .order_by(Record.created_at.desc(), Record.id).offset(offset).limit(limit)))
    count = db.scalar(select(func.count()).select_from(Record).where(Record.user_id == user.id, Record.kind == "observation"))
    return {"items": [repo.view(row) for row in rows], "total": count, "offset": offset, "limit": limit}


@router.post("/me/observations/{record_id}/revisions", status_code=201)
def revise_observation(record_id: str, body: Revision, user=Depends(get_current_user), db=Depends(get_db)):
    repo.consent(db, user.id, "health_data_processing")
    row = repo.own(db, user.id, record_id, "observation")
    original = unseal(row.payload)
    if original["provenance"] != "observed":
        raise HTTPException(409, "Report observations require source report review")
    if row.version != 1:
        raise HTTPException(409, "This observation already has a correction; edit its latest revision")
    if body.unit.lower() not in FIELDS[original["field"]]["units"]:
        raise HTTPException(422, "Unsupported unit")
    result = db.execute(update(Record).where(Record.id == row.id, Record.version == 1)
                        .values(version=2).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "Observation changed; reload")
    recorded_at = max(utcnow(), datetime.fromisoformat(original["recorded_at"]) + timedelta(microseconds=1))
    data = {**original, "observation_id": uid(), "value": body.value, "unit": body.unit,
            "recorded_at": recorded_at.isoformat(), "supersedes_observation_id": original["observation_id"],
            "audit_metadata": {"actor_id": user.id, "reason": body.reason}, "quality_flags": []}
    revision = repo.create(db, user.id, "observation", data, parent_id=row.parent_id)
    invalidate_goals(db, user.id, "measurements_changed")
    repo.audit(db, user.id, user.id, "measurement.corrected", revision.id, {"previous_id": row.id, "reason": body.reason})
    db.commit()
    return repo.view(revision)


@router.get("/me/progress", responses={200: {"content": {"application/json": {"schema": summary_schemas()["body_progress_dashboard"]}}}})
def get_progress(user=Depends(get_current_user), db=Depends(get_db)):
    return dashboard_payload(repo.progress(db, user.id), user.id)


@router.get("/me/planner-context", responses={200: {"content": {"application/json": {"schema": summary_schemas()["body_progress_planner_context"]}}}})
def get_planner_context(user=Depends(get_current_user), db=Depends(get_db), stream_id: list[str] = Query(default=[])):
    try:
        return planner_context(repo.progress(db, user.id), user.id, stream_id)
    except ValueError as error:
        raise HTTPException(422, str(error))


def inspect_upload(raw):
    if raw.startswith(b"%PDF-"):
        try:
            with pdfium.PdfDocument(raw) as pdf:
                if not 1 <= len(pdf) <= 5:
                    raise ValueError("PDF must have 1–5 pages")
                for index in range(len(pdf)):
                    with pdf[index] as page:
                        width, height = page.get_size()
                        if width <= 0 or height <= 0 or width * height > 25_000_000:
                            raise ValueError("PDF page exceeds size limit")
        except Exception as error:
            raise HTTPException(422, "Invalid, encrypted, or oversized PDF") from error
        return "application/pdf", "pdf"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                fmt = image.format
                if fmt not in ("JPEG", "PNG") or image.width * image.height > 25_000_000 or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Expected JPEG/PNG within 25 megapixels")
                image.verify()
            with Image.open(BytesIO(raw)) as image:
                image.load()
    except Exception as error:
        raise HTTPException(422, "Invalid JPEG/PNG or image exceeds size limit") from error
    return ("image/jpeg", "jpg") if fmt == "JPEG" else ("image/png", "png")


@router.post("/me/documents", status_code=201, openapi_extra={"requestBody": {"required": True, "content": {
    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
async def upload_document(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    repo.consent(db, user.id, "health_data_processing")
    grant = repo.consent(db, user.id, "document_processing")
    # A raw streamed body avoids multipart spooling plaintext to temporary files.
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise HTTPException(413, "Document exceeds the upload limit")
        chunks.append(chunk)
    raw = b"".join(chunks)
    mime, extension = await run_in_threadpool(inspect_upload, raw)
    row = repo.create(db, user.id, "document", {"mime": mime, "extension": extension, "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(), "consent_id": grant.id,
        "expires_at": (utcnow() + timedelta(days=settings.document_retention_days)).isoformat()})
    path = blob_path(row.id)
    try:
        path.write_bytes(vault().encrypt(raw))
        repo.audit(db, user.id, user.id, "document.uploaded", row.id)
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return repo.view(row)


def active_document(db, user_id, document_id):
    row = repo.own(db, user_id, document_id, "document")
    if datetime.fromisoformat(unseal(row.payload)["expires_at"]) <= utcnow():
        raise HTTPException(410, "Source report expired; remove it or upload a new copy")
    return row


@router.get("/me/documents")
def list_documents(user=Depends(get_current_user), db=Depends(get_db)):
    return [repo.view(row) for row in repo.records(db, user.id, "document")]


@router.get("/me/documents/{document_id}/content")
def document_content(document_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    row = active_document(db, user.id, document_id)
    data = unseal(row.payload)
    path = blob_path(row.id)
    if not path.is_file():
        raise HTTPException(410, "Source file is unavailable")
    repo.audit(db, user.id, user.id, "document.downloaded", row.id)
    db.commit()
    return Response(vault().decrypt(path.read_bytes()), media_type=data["mime"],
                    headers={"Content-Disposition": f'attachment; filename="report.{data["extension"]}"',
                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def erase_document(db, row, actor):
    blob_path(row.id).unlink(missing_ok=True)
    repo.audit(db, row.user_id, actor, "document.deleted", row.id)
    db.delete(row)
    invalidate_goals(db, row.user_id, "source_document_deleted")


@router.delete("/me/documents/{document_id}", status_code=204)
def delete_document(document_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    row = repo.own(db, user.id, document_id, "document")
    erase_document(db, row, user.id)
    db.commit()


@router.post("/me/documents/{document_id}/ocr")
def request_ocr(document_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    repo.own(db, user.id, document_id, "document")
    repo.consent(db, user.id, "document_processing")
    raise HTTPException(409, "OCR release gate pending. Use manual transcription and review")


def draft_view(row):
    data = repo.view(row)
    extraction = data["extraction"]
    selected = [key for key in REPORT_FIELDS if extraction[key] is not None]
    flags = set(validate_values({key: extraction[key] for key in REPORT_FIELDS}))
    flags = {flag for flag in flags if flag.split(":")[0] in selected}
    for key in selected:
        flags.update(f"{key}:{flag}" for flag in extraction["field_evidence"][key]["flags"])
    flags.update(flag for flag in extraction["quality_flags"] if flag.startswith("measured_at:"))
    return {**data, "required_acknowledgements": sorted(flags)}


@router.post("/me/documents/{document_id}/transcription", status_code=201)
def transcribe(document_id: str, body: Transcription, user=Depends(get_current_user), db=Depends(get_db)):
    repo.consent(db, user.id, "health_data_processing")
    repo.consent(db, user.id, "document_processing")
    active_document(db, user.id, document_id)
    previous = db.scalars(select(Record).where(Record.document_id == document_id, Record.kind == "report_draft"))
    if any(unseal(item.payload)["status"] == "confirmed_by_user" for item in previous):
        raise HTTPException(409, "A review is already confirmed for this source. Remove the source before replacing it")
    if not repo.singleton(db, user.id, "profile"):
        raise HTTPException(409, "Complete your profile first")
    validate_units(body.values)
    if any(value.field not in REPORT_FIELDS for value in body.values):
        raise HTTPException(422, "Unsupported report field")
    extraction = parse_lines([], document_id=document_id, model_version="manual-transcription-v1")
    extraction["measured_at"] = body.measured_on.isoformat() if body.measured_on else None
    extraction["quality_flags"] = [] if body.measured_on else ["measured_at:missing"]
    extraction["device_model"] = body.device_model
    for value in body.values:
        spec = REPORT_FIELDS[value.field]
        extraction[value.field] = round(value.value * spec["units"][value.unit.lower()], 9)
        extraction["field_evidence"][value.field] = {"unit": spec["unit"], "candidates": [],
                                                       "flags": ["manual_transcription_unverified"]}
    row = repo.create(db, user.id, "report_draft", {"extraction": extraction, "status": "pending_user_review",
        "device_id": body.device_id, "device_model": body.device_model, "protocol_id": body.protocol_id}, document_id=document_id)
    repo.audit(db, user.id, user.id, "report.transcribed", row.id)
    db.commit()
    return draft_view(row)


@router.get("/me/report-drafts/{draft_id}")
def get_draft(draft_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    return draft_view(repo.own(db, user.id, draft_id, "report_draft"))


@router.get("/me/report-drafts")
def list_drafts(user=Depends(get_current_user), db=Depends(get_db)):
    return [{**draft_view(row), "document_id": row.document_id} for row in repo.records(db, user.id, "report_draft")]


@router.post("/me/report-drafts/{draft_id}/confirm", status_code=201)
def confirm_report(draft_id: str, body: ConfirmDraft, user=Depends(get_current_user), db=Depends(get_db)):
    grant = repo.consent(db, user.id, "health_data_processing")
    repo.consent(db, user.id, "document_processing")
    row = repo.own(db, user.id, draft_id, "report_draft")
    active_document(db, user.id, row.document_id)
    data = unseal(row.payload)
    if data["status"] != "pending_user_review":
        raise HTTPException(409, "This draft has already been confirmed")
    # Lock the source document as well, preventing two pending drafts for the same
    # report from being confirmed concurrently (including across API workers).
    source = repo.own(db, user.id, row.document_id, "document")
    if source.version != 1:
        raise HTTPException(409, "This source report already has a confirmed review")
    source_lock = db.execute(update(Record).where(Record.id == source.id, Record.version == 1)
                            .values(version=2).execution_options(synchronize_session=False))
    if source_lock.rowcount != 1:
        raise HTTPException(409, "This source report already has a confirmed review")
    try:
        review = confirm_fields(data["extraction"], reviewer_id=user.id, selected_fields=body.selected_fields,
                                corrections=body.corrections, acknowledged_flags=body.acknowledged_flags, processing_consent=True)
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(422, str(error))
    # Keep the full review with the source draft, so source deletion removes its values.
    result = db.execute(update(Record).where(Record.id == row.id, Record.version == body.version)
        .values(payload=seal({**data, "status": "confirmed_by_user", "review": review}), version=Record.version + 1,
                updated_at=utcnow()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise HTTPException(409, "Draft changed. Reload before confirming")
    session = repo.create(db, user.id, "measurement_session", {"source": "inbody", "review_id": review["review_id"]}, document_id=row.document_id)
    profile = repo.singleton(db, user.id, "profile")
    rows = observations_from_review(review, subject_id=user.id, session_id=session.id, device_id=data["device_id"],
        device_model=data["device_model"], measurement_timezone=unseal(profile.payload)["timezone"],
        protocol_id=data["protocol_id"], consent_id=grant.id)
    for item in rows:
        # This workflow-state flag is resolved by explicit review. Engineering
        # plausibility and date flags remain, and the original draft stays intact.
        item["quality_flags"] = [flag for flag in item["quality_flags"] if not flag.endswith(":manual_transcription_unverified")]
    result = [repo.view(repo.create(db, user.id, "observation", item, parent_id=session.id, document_id=row.document_id)) for item in rows]
    invalidate_goals(db, user.id, "measurements_changed")
    repo.audit(db, user.id, user.id, "report.confirmed", row.id)
    db.commit()
    return {"observations": result, "review_id": review["review_id"]}


@router.get("/me/goals")
def list_goals(user=Depends(get_current_user), db=Depends(get_db)):
    return [repo.view(row) for row in repo.records(db, user.id, "goal")]


@router.post("/me/goals", status_code=201)
def create_goal(body: GoalInput, user=Depends(get_current_user), db=Depends(get_db)):
    result = screen_goal(db, user.id, body, dashboard_payload(repo.progress(db, user.id), user.id))
    row = repo.create(db, user.id, "goal", result)
    repo.audit(db, user.id, user.id, "goal.approved", row.id, {"after": result})
    db.commit()
    return repo.view(row)


@router.put("/me/goals/{goal_id}")
def revise_goal(goal_id: str, body: GoalRevision, user=Depends(get_current_user), db=Depends(get_db)):
    row = repo.own(db, user.id, goal_id, "goal")
    result = screen_goal(db, user.id, body, dashboard_payload(repo.progress(db, user.id), user.id))
    repo.replace(db, row, body.version, result, user.id, body.reason)
    db.commit()
    return repo.view(row)


@router.get("/me/goals/{goal_id}/history")
def goal_history(goal_id: str, user=Depends(get_current_user), db=Depends(get_db)):
    repo.own(db, user.id, goal_id, "goal")
    rows = db.scalars(select(Audit).where(Audit.subject_id == user.id, Audit.entity_id == goal_id).order_by(Audit.created_at))
    return [{"action": row.action, "recorded_at": aware(row.created_at).isoformat(), **unseal(row.payload)} for row in rows]


@router.get("/me/export")
def export_account(user=Depends(get_current_user), db=Depends(get_db)):
    rows = list(db.scalars(select(Record).where(Record.user_id == user.id).order_by(Record.created_at)))
    consents = list(db.scalars(select(Consent).where(Consent.user_id == user.id).order_by(Consent.created_at)))
    audits = list(db.scalars(select(Audit).where(Audit.subject_id == user.id).order_by(Audit.created_at)))
    repo.audit(db, user.id, user.id, "account.exported", user.id)
    db.commit()
    return JSONResponse({"export_version": "1", "exported_at": utcnow().isoformat(),
        "user": {"id": user.id, "email": user.email, "role": user.role},
        "records": [{"kind": row.kind, "document_id": row.document_id, "parent_id": row.parent_id, **repo.view(row)} for row in rows],
        "consents": [{"id": row.id, "purpose": row.purpose, "granted": row.granted, "policy_version": row.policy_version,
                      "recorded_at": aware(row.created_at).isoformat()} for row in consents],
        "audit": [{"id": row.id, "action": row.action, "actor_id": row.actor_id, "entity_id": row.entity_id,
                   "recorded_at": aware(row.created_at).isoformat(), **unseal(row.payload)} for row in audits],
        "files": [{"document_id": row.id, "download_path": f"/api/v1/me/documents/{row.id}/content"} for row in rows if row.kind == "document"]},
        headers={"Content-Disposition": 'attachment; filename="health-export.json"', "Cache-Control": "no-store"})


@router.delete("/me/account", status_code=204)
def delete_account(body: Reauthenticate, response: Response, user=Depends(get_current_user), db=Depends(get_db)):
    if not password_valid(user.password_hash, body.password):
        raise HTTPException(401, "Password verification failed")
    for row in repo.records(db, user.id, "document"):
        blob_path(row.id).unlink(missing_ok=True)
    db.delete(user)
    db.commit()
    response.delete_cookie("health_session", path="/")


@router.get("/admin/overview", tags=["admin"])
def admin_overview(user=Depends(require_admin), db=Depends(get_db)):
    return {"users": db.scalar(select(func.count()).select_from(User)),
            "documents": db.scalar(select(func.count()).select_from(Record).where(Record.kind == "document")),
            "observations": db.scalar(select(func.count()).select_from(Record).where(Record.kind == "observation")),
            "capabilities": capabilities()}


@router.get("/admin/users", tags=["admin"])
def admin_users(user=Depends(require_admin), db=Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    rows = db.scalars(select(User).order_by(User.created_at.desc()).offset(offset).limit(limit))
    return {"items": [{"id": row.id, "email": row.email, "role": row.role,
                       "support_access": bool(repo.consent(db, row.id, "admin_support", False))} for row in rows],
            "total": db.scalar(select(func.count()).select_from(User)), "offset": offset, "limit": limit}


@router.get("/admin/users/{subject_id}/support-profile", tags=["admin"])
def support_profile(subject_id: str, user=Depends(require_admin), db=Depends(get_db)):
    if not db.get(User, subject_id):
        raise HTTPException(404, "User not found")
    repo.consent(db, subject_id, "admin_support")
    row = repo.singleton(db, subject_id, "profile")
    repo.audit(db, subject_id, user.id, "admin.support_profile_viewed", subject_id)
    db.commit()
    return {"profile": repo.view(row) if row else None, "read_only": True}
