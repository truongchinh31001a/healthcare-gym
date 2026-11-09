from datetime import timedelta
from io import BytesIO
from PIL import Image
from sqlalchemy import select, func
from app.models import User, Record, CredentialSession, Audit, Consent, utcnow
from app.core.vault import blob_path, unseal
from conftest import PASSWORD, register, grant, profile


def measurement(client, headers, value=70, days=0, **changes):
    return client.post("/api/v1/me/measurement-sessions", headers=headers, json={
        "measured_at": (utcnow()-timedelta(days=days, minutes=1)).isoformat(),
        "values": [{"field": "weight_kg", "value": value, "unit": "kg"}],
        "device_id": "scale-1", "device_model": "demo-scale", "protocol_id": "morning-v1",
        "measurement_method": "scale", **changes})


def upload(client, headers):
    stream = BytesIO()
    Image.new("RGB", (20, 20), "white").save(stream, format="PNG")
    raw = stream.getvalue()
    result = client.post("/api/v1/me/documents", content=raw, headers={**headers, "Content-Type": "application/octet-stream"})
    assert result.status_code == 201, result.text
    return result.json(), raw


def draft(client, headers, document_id, value=70):
    result = client.post(f"/api/v1/me/documents/{document_id}/transcription", headers=headers, json={
        "values": [{"field": "weight_kg", "value": value, "unit": "kg"}], "measured_on": "2026-01-01",
        "device_id": "bia-1", "device_model": "demo-bia", "protocol_id": "report-v1"})
    assert result.status_code == 201, result.text
    return result.json()


def confirm(client, headers, data, **changes):
    return client.post(f'/api/v1/me/report-drafts/{data["id"]}/confirm', headers=headers, json={
        "version": data["version"], "selected_fields": ["weight_kg"], "checked_original": True,
        "acknowledged_flags": data["required_acknowledgements"], **changes})


def test_registration_cannot_assign_admin(setup):
    client, _ = setup
    body = {"email": "test@example.com", "password": PASSWORD, "adult_attestation": True, "role": "admin"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 422
    body.pop("role")
    body["adult_attestation"] = False
    assert client.post("/api/v1/auth/register", json=body).status_code == 422


def test_tokens_hashed_revoked_and_expired(account):
    client, factory, headers, _ = account
    with factory() as db:
        token = db.scalar(select(CredentialSession))
        assert token.token_hash != headers["Authorization"][7:]
        token.expires_at = utcnow()-timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/me/profile", headers=headers).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD}).json()
    headers = {"Authorization": "Bearer " + login["access_token"]}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/me/profile", headers=headers).status_code == 401


def test_web_cookie_csrf_and_origin(account):
    client, _, _, _ = account
    login = client.post("/api/v1/auth/login", json={"email": "person@example.com", "password": PASSWORD, "client": "web"})
    assert login.json()["access_token"] is None
    assert "HttpOnly" in login.headers["set-cookie"]
    body = {"purpose": "research_training", "granted": True}
    assert client.post("/api/v1/me/consents", json=body).status_code == 403
    headers = {"Origin": "https://evil.example", "X-CSRF-Token": login.json()["csrf_token"]}
    assert client.post("/api/v1/me/consents", headers=headers, json=body).status_code == 403
    headers["Origin"] = "http://localhost:3000"
    assert client.post("/api/v1/me/consents", headers=headers, json=body).status_code == 201


def test_login_rate_limit_and_generic_failure(setup):
    client, _ = setup
    for _ in range(10):
        result = client.post("/api/v1/auth/login", json={"email": "absent@example.com", "password": PASSWORD})
        assert result.status_code == 401
        assert result.json()["detail"] == "Invalid email or password"
    assert client.post("/api/v1/auth/login", json={"email": "absent@example.com", "password": PASSWORD}).status_code == 429


def test_separate_consent_revocation_and_access_rights(setup):
    client, _ = setup
    headers, _ = register(client)
    assert profile(client, headers).status_code == 403
    grant(client, headers)
    assert profile(client, headers).status_code == 200
    consents = client.get("/api/v1/me/consents", headers=headers).json()
    assert not next(c["granted"] for c in consents if c["purpose"] == "research_training")
    grant(client, headers, granted=False)
    assert measurement(client, headers).status_code == 403
    assert client.get("/api/v1/me/progress", headers=headers).status_code == 403
    assert client.get("/api/v1/me/export", headers=headers).status_code == 200
    assert client.get("/api/v1/me/profile", headers=headers).status_code == 200


def test_profile_validation_version_and_encryption(account):
    client, factory, headers, _ = account
    assert profile(client, headers).status_code == 409
    assert profile(client, headers, version=1, timezone="not/a-zone").status_code == 422
    assert profile(client, headers, version=1, birth_date=utcnow().date().isoformat()).status_code == 422
    assert profile(client, headers, version=1, height_cm=172).status_code == 200
    with factory() as db:
        rows = db.scalars(select(Record)).all()
        assert "Synthetic Adult" not in rows[0].payload
        assert unseal(rows[0].payload)["height_cm"] == 172
        history = db.scalars(select(Audit).where(Audit.action == "profile.updated")).one()
        assert unseal(history.payload)["before"]["height_cm"] == 170


def test_owner_and_admin_support_consent(account):
    client, factory, headers, user = account
    item = measurement(client, headers).json()["observations"][0]
    other_headers, other = register(client, "other@example.com")
    grant(client, other_headers)
    assert client.post(f'/api/v1/me/observations/{item["id"]}/revisions', headers=other_headers,
                       json={"value": 71, "unit": "kg", "reason": "Correct reading"}).status_code == 404
    assert client.get("/api/v1/admin/users", headers=other_headers).status_code == 403
    assert client.get("/api/v1/admin/metrics", headers=other_headers).status_code == 403
    with factory() as db:
        db.get(User, other["id"]).role = "admin"
        db.commit()
    assert client.get("/api/v1/admin/metrics", headers=other_headers).status_code == 200
    assert client.get(f'/api/v1/admin/users/{user["id"]}/support-profile', headers=other_headers).status_code == 403
    grant(client, headers, "admin_support")
    assert client.get(f'/api/v1/admin/users/{user["id"]}/support-profile', headers=other_headers).status_code == 200
    export = client.get("/api/v1/me/export", headers=headers).json()
    assert any(a["action"] == "admin.support_profile_viewed" for a in export["audit"])
    grant(client, headers, "admin_support", False)
    assert client.get(f'/api/v1/admin/users/{user["id"]}/support-profile', headers=other_headers).status_code == 403


def test_measurement_dates_units_provenance_and_revisions(account):
    client, _, headers, _ = account
    assert measurement(client, headers, measured_at="2026-01-01T10:00:00").status_code == 422
    assert measurement(client, headers, measured_at=(utcnow()+timedelta(days=1)).isoformat()).status_code == 422
    assert measurement(client, headers, values=[{"field": "weight_kg", "value": 70, "unit": "cm"}]).status_code == 422
    item = measurement(client, headers, values=[{"field": "weight_kg", "value": 154, "unit": "lb"}]).json()["observations"][0]
    assert item["provenance"] == "observed"
    result = client.get("/api/v1/me/progress", headers=headers).json()
    assert abs(result["series"][0]["latest"]["value"] - 154*.45359237) < 1e-6
    revision = {"value": 155, "unit": "lb", "reason": "Read scale again"}
    assert client.post(f'/api/v1/me/observations/{item["id"]}/revisions', headers=headers, json=revision).status_code == 201
    assert client.post(f'/api/v1/me/observations/{item["id"]}/revisions', headers=headers, json=revision).status_code == 409
    result = client.get("/api/v1/me/progress", headers=headers).json()
    assert abs(result["series"][0]["latest"]["value"] - 155*.45359237) < 1e-6


def test_trend_support_and_outlier_preserved(account):
    client, _, headers, _ = account
    for days in (21, 14, 7, 0):
        assert measurement(client, headers, value=70+days*.04, days=days).status_code == 201
    result = client.get("/api/v1/me/progress", headers=headers).json()
    assert result["series"][0]["trend"]["status"] == "descriptive_only"
    assert abs(result["series"][0]["trend"]["slope_per_week"] + .28) < 1e-6
    assert measurement(client, headers, 700).status_code == 201
    result = client.get("/api/v1/me/progress", headers=headers).json()
    assert result["series"][0]["active_observations"] == 5
    assert "outside_plausibility_bounds" in result["series"][0]["historical_audit_flags"]
    assert result["series"][0]["trend"]["status"] == "withheld"


def test_document_validation_encryption_download_and_gates(account):
    client, _, headers, _ = account
    assert client.post("/api/v1/me/documents", headers=headers, content=b"fake").status_code == 403
    grant(client, headers, "document_processing")
    assert client.post("/api/v1/me/documents", headers=headers, content=b"fake").status_code == 422
    document, raw = upload(client, headers)
    assert raw not in blob_path(document["id"]).read_bytes()
    result = client.get(f'/api/v1/me/documents/{document["id"]}/content', headers=headers)
    assert result.content == raw and result.headers["content-disposition"].startswith("attachment")
    assert client.post(f'/api/v1/me/documents/{document["id"]}/ocr', headers=headers).status_code == 409


def test_report_pending_review_replay_and_delete(account):
    client, factory, headers, _ = account
    grant(client, headers, "document_processing")
    document, _ = upload(client, headers)
    data = draft(client, headers, document["id"])
    assert client.get("/api/v1/me/observations", headers=headers).json()["total"] == 0
    assert confirm(client, headers, data, acknowledged_flags=[]).status_code == 422
    result = confirm(client, headers, data)
    assert result.status_code == 201, result.text
    observation = result.json()["observations"][0]
    assert observation["provenance"] == "extracted" and observation["verification_status"] == "confirmed_by_user"
    assert observation["measured_at"] == "2026-01-01"
    assert confirm(client, headers, data).status_code == 409
    assert client.delete(f'/api/v1/me/documents/{document["id"]}', headers=headers).status_code == 204
    assert not blob_path(document["id"]).exists()
    assert client.get("/api/v1/me/observations", headers=headers).json()["total"] == 0
    assert client.get(f'/api/v1/me/report-drafts/{data["id"]}', headers=headers).status_code == 404
    with factory() as db:
        assert all("extraction" not in unseal(row.payload) for row in db.scalars(select(Audit)))


def test_safety_unknown_positive_and_goal_approval(account):
    client, _, headers, _ = account
    body = {"target_weight_kg": 68, "weeks": 12, "approved_by_user": True}
    result = client.post("/api/v1/me/goals", headers=headers, json=body)
    assert result.status_code == 201, result.text
    assert result.json()["status"] == "needs_information"
    assert "unknown:pregnancy" in result.json()["reasons"]
    assert client.post("/api/v1/me/goals", headers=headers, json={**body, "approved_by_user": False}).status_code == 422
    context = {"pregnancy": "yes", "eating_disorder_risk": "no", "clinician_restrictions": "no", "acute_red_flags": "no"}
    assert client.put("/api/v1/me/health-context", headers=headers, json=context).status_code == 200
    assert client.post("/api/v1/me/goals", headers=headers, json=body).json()["status"] == "needs_professional_review"


def test_goal_activation_history_and_rescreening(account):
    client, _, headers, _ = account
    for days in (21, 14, 7, 0):
        assert measurement(client, headers, 70+days*.04, days).status_code == 201
    context = {k: "no" for k in ("pregnancy", "eating_disorder_risk", "clinician_restrictions", "acute_red_flags")}
    assert client.put("/api/v1/me/health-context", headers=headers, json=context).status_code == 200
    body = {"target_weight_kg": 68, "weeks": 12, "approved_by_user": True}
    result = client.post("/api/v1/me/goals", headers=headers, json=body)
    assert result.status_code == 201, result.text
    goal = result.json()
    assert goal["status"] == "active"
    updated = client.put(f'/api/v1/me/goals/{goal["id"]}', headers=headers, json={**body, "target_weight_kg": 67,
        "version": goal["version"], "reason": "User changed target"})
    assert updated.status_code == 200, updated.text
    assert client.get(f'/api/v1/me/goals/{goal["id"]}/history', headers=headers).json()[-1]["before"]["target_weight_kg"] == 68
    assert client.put("/api/v1/me/health-context", headers=headers, json={**context, "version": 1, "pregnancy": "unknown"}).status_code == 200
    assert client.get("/api/v1/me/goals", headers=headers).json()[0]["status"] == "needs_rescreening"


def test_account_export_and_complete_deletion(account):
    client, factory, headers, user = account
    grant(client, headers, "document_processing")
    document, _ = upload(client, headers)
    assert measurement(client, headers).status_code == 201
    exported = client.get("/api/v1/me/export", headers=headers).json()
    assert exported["records"] and exported["files"]
    assert "password_hash" not in str(exported) and "token_hash" not in str(exported)
    assert client.request("DELETE", "/api/v1/me/account", headers=headers, json={"password": "wrong"}).status_code == 401
    assert client.request("DELETE", "/api/v1/me/account", headers=headers, json={"password": PASSWORD}).status_code == 204
    assert not blob_path(document["id"]).exists()
    assert client.get("/api/v1/me/profile", headers=headers).status_code == 401
    with factory() as db:
        assert db.get(User, user["id"]) is None
        for model in (Record, CredentialSession, Audit, Consent):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_request_bounds_and_nonfinite_json(account, monkeypatch):
    from app.core.config import settings
    client, _, headers, _ = account
    assert client.put("/api/v1/me/profile", headers={**headers, "Content-Type": "application/json"},
                      content=b'{"height_cm": NaN}').status_code == 400
    assert client.put("/api/v1/me/profile", headers={**headers, "Content-Type": "application/json"},
                      content=b'{"height_cm": 1e999}').status_code == 400
    assert measurement(client, headers, 1e308).status_code == 422
    assert client.post("/api/v1/auth/login", headers={"Content-Type": "application/json"}, content=b"{broken}").status_code == 400
    assert client.post("/api/v1/auth/login", content=b"x"*(1024*1024+1)).status_code == 413
    grant(client, headers, "document_processing")
    monkeypatch.setattr(settings, "max_upload_bytes", 50)
    assert client.post("/api/v1/me/documents", headers=headers, content=b"x"*51).status_code == 413
    def chunks():
        yield b"x"*40
        yield b"x"*40
    assert client.post("/api/v1/me/documents", headers=headers, content=chunks()).status_code == 413


def test_file_and_draft_access_cannot_cross_accounts(account):
    client, _, headers, _ = account
    grant(client, headers, "document_processing")
    document, _ = upload(client, headers)
    data = draft(client, headers, document["id"])
    other, _ = register(client, "other@example.com")
    grant(client, other)
    grant(client, other, "document_processing")
    assert client.get(f'/api/v1/me/documents/{document["id"]}/content', headers=other).status_code == 404
    assert client.delete(f'/api/v1/me/documents/{document["id"]}', headers=other).status_code == 404
    assert client.get(f'/api/v1/me/report-drafts/{data["id"]}', headers=other).status_code == 404
    assert confirm(client, other, data).status_code == 404
    assert client.get("/api/v1/me/report-drafts", headers=other).json() == []


def test_consent_revocation_blocks_pending_confirmation(account):
    client, _, headers, _ = account
    grant(client, headers, "document_processing")
    document, _ = upload(client, headers)
    data = draft(client, headers, document["id"])
    grant(client, headers, "document_processing", False)
    assert confirm(client, headers, data).status_code == 403
    grant(client, headers, "document_processing", True)
    assert confirm(client, headers, data).status_code == 201


def test_source_is_confirmed_once_across_different_drafts(account):
    client, _, headers, _ = account
    grant(client, headers, "document_processing")
    document, _ = upload(client, headers)
    first = draft(client, headers, document["id"])
    second = draft(client, headers, document["id"])
    assert confirm(client, headers, first).status_code == 201
    assert confirm(client, headers, second).status_code == 409
    assert client.get("/api/v1/me/observations", headers=headers).json()["total"] == 1


def test_retention_dry_run_and_cascade(account):
    from app.maintenance import purge_expired
    from app.core.vault import seal
    client, factory, headers, _ = account
    grant(client, headers, "document_processing")
    document, _ = upload(client, headers)
    data = draft(client, headers, document["id"])
    assert confirm(client, headers, data).status_code == 201
    with factory() as db:
        row = db.get(Record, document["id"])
        row.payload = seal({**unseal(row.payload), "expires_at": (utcnow()-timedelta(days=1)).isoformat()})
        db.commit()
        assert purge_expired(db) == 1
        assert blob_path(document["id"]).is_file()
        assert purge_expired(db, apply=True) == 1
    assert not blob_path(document["id"]).exists()
    assert client.get("/api/v1/me/observations", headers=headers).json()["total"] == 0


def test_unknown_date_never_becomes_upload_date(account):
    client, _, headers, _ = account
    grant(client, headers, "document_processing")
    document, _ = upload(client, headers)
    result = client.post(f'/api/v1/me/documents/{document["id"]}/transcription', headers=headers, json={
        "values": [{"field": "weight_kg", "value": 70, "unit": "kg"}],
        "device_id": "bia-1", "device_model": "demo", "protocol_id": "report-v1"})
    data = result.json()
    result = confirm(client, headers, data)
    assert result.status_code == 201
    assert result.json()["observations"][0]["measured_at"] is None
    series = client.get("/api/v1/me/progress", headers=headers).json()["series"][0]
    assert series["latest"] is None and series["trend"]["status"] == "withheld"


def test_dashboard_and_planner_contracts(account):
    from jsonschema import Draft202012Validator
    from health_core.body_progress.contracts import summary_schemas
    client, _, headers, _ = account
    assert measurement(client, headers).status_code == 201
    for route, schema in (("progress", "body_progress_dashboard"), ("planner-context", "body_progress_planner_context")):
        payload = client.get("/api/v1/me/"+route, headers=headers).json()
        Draft202012Validator(summary_schemas()[schema]).validate(payload)


def test_multiple_sources_require_explicit_goal_choice(account):
    client, _, headers, _ = account
    for device in ("scale-1", "scale-2"):
        for days in (21, 14, 7, 0):
            assert measurement(client, headers, 70+days*.04, days, device_id=device).status_code == 201
    context = {k: "no" for k in ("pregnancy", "eating_disorder_risk", "clinician_restrictions", "acute_red_flags")}
    client.put("/api/v1/me/health-context", headers=headers, json=context)
    body = {"target_weight_kg": 68, "weeks": 12, "approved_by_user": True}
    assert client.post("/api/v1/me/goals", headers=headers, json=body).json()["status"] == "needs_information"
    stream = client.get("/api/v1/me/progress", headers=headers).json()["series"][0]["stream_id"]
    assert client.post("/api/v1/me/goals", headers=headers, json={**body, "weight_stream_id": stream}).json()["status"] == "active"
    assert client.post("/api/v1/me/goals", headers=headers, json={**body, "weight_stream_id": "0"*20}).json()["status"] == "needs_information"


def test_limits_are_rule_screening_and_not_medical_clearance(account):
    client, _, headers, _ = account
    for days in (21, 14, 7, 0):
        measurement(client, headers, 70+days*.04, days)
    context = {k: "no" for k in ("pregnancy", "eating_disorder_risk", "clinician_restrictions", "acute_red_flags")}
    client.put("/api/v1/me/health-context", headers=headers, json=context)
    body = {"target_weight_kg": 40, "weeks": 1, "approved_by_user": True}
    result = client.post("/api/v1/me/goals", headers=headers, json=body).json()
    assert result["status"] == "needs_professional_review"
    assert result["medical_clearance"] is False and result["automatic_plan_authorized"] is False
    capabilities = client.get("/api/v1/capabilities", headers=headers).json()
    assert not capabilities["ocr"]["enabled"] and not capabilities["body_cv"]["enabled"]


def test_revision_survives_equal_resolution_server_clock(account, monkeypatch):
    from datetime import datetime
    client, _, headers, _ = account
    original = measurement(client, headers).json()["observations"][0]
    monkeypatch.setattr("app.modules.health_profile.router.utcnow", lambda: datetime.fromisoformat(original["recorded_at"]))
    revised = client.post(f'/api/v1/me/observations/{original["id"]}/revisions', headers=headers,
                          json={"value": 71, "unit": "kg", "reason": "Correct reading"})
    assert revised.status_code == 201
    assert revised.json()["recorded_at"] > original["recorded_at"]
    result = client.get("/api/v1/me/progress", headers=headers).json()
    assert result["series"][0]["latest"]["value"] == 71


def test_production_rejects_insecure_configuration(monkeypatch, tmp_path):
    import pytest
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.config import settings
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    monkeypatch.setattr(settings, "encryption_key", None)
    monkeypatch.setattr(settings, "database_url", "sqlite+pysqlite://")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        with TestClient(app):
            pass
    monkeypatch.setattr(settings, "database_url", "postgresql+psycopg://unused")
    monkeypatch.setattr(settings, "cors_origins", ["http://localhost:3000"])
    with pytest.raises(RuntimeError, match="HTTPS"):
        with TestClient(app):
            pass
    monkeypatch.setattr(settings, "cors_origins", ["https://admin.example.com"])
    with pytest.raises(RuntimeError, match="ENCRYPTION_KEY"):
        with TestClient(app):
            pass
