"""Synthetic HTTP E2E demo. Creates a temporary local account and deletes it in finally."""
import argparse
from datetime import datetime, timezone, timedelta
from io import BytesIO
import json
from pathlib import Path
import secrets
from urllib.parse import urlparse
import httpx
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--api-url", default="http://127.0.0.1:8000")
parser.add_argument("--report", type=Path)
args = parser.parse_args()
if urlparse(args.api_url).hostname not in ("127.0.0.1", "localhost", "::1"):
    raise SystemExit("This synthetic smoke script only targets a local server")
email = "synthetic-" + secrets.token_hex(6) + "@example.com"
password = secrets.token_urlsafe(24)
steps, headers = [], {}

with httpx.Client(base_url=args.api_url, timeout=30) as client:
    def call(method, path, expected=200, **kwargs):
        response = client.request(method, "/api/v1" + path, headers=headers, **kwargs)
        if response.status_code != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, received {response.status_code}")
        steps.append({"method": method, "step": path.split("/")[-1], "status": response.status_code})
        return response.json() if response.content else None
    try:
        call("POST", "/auth/register", 201, json={"email": email, "password": password, "adult_attestation": True})
        session = call("POST", "/auth/login", json={"email": email, "password": password, "client": "mobile"})
        headers = {"Authorization": "Bearer " + session["access_token"]}
        for purpose in ("health_data_processing", "document_processing"):
            call("POST", "/me/consents", 201, json={"purpose": purpose, "granted": True})
        call("PUT", "/me/profile", json={"display_name": "Synthetic E2E adult", "birth_date": "1995-01-01", "height_cm": 170, "timezone": "Asia/Bangkok"})
        for days in (21, 14, 7, 0):
            call("POST", "/me/measurement-sessions", 201, json={
                "measured_at": (datetime.now(timezone.utc)-timedelta(days=days, minutes=1)).isoformat(),
                "values": [{"field": "weight_kg", "value": 70+days*.04, "unit": "kg"}],
                "device_id": "synthetic-scale-1", "device_model": "synthetic-scale", "protocol_id": "synthetic-morning-v1", "measurement_method": "scale"})
        progress = call("GET", "/me/progress")
        assert progress["series"][0]["trend"]["status"] == "descriptive_only"
        call("PUT", "/me/health-context", json={key: "no" for key in
            ("pregnancy", "eating_disorder_risk", "clinician_restrictions", "acute_red_flags")})
        goal = call("POST", "/me/goals", 201, json={"target_weight_kg": 68, "weeks": 12, "approved_by_user": True})
        assert goal["status"] == "active" and goal["automatic_plan_authorized"] is False
        stream = BytesIO()
        Image.new("RGB", (160, 100), "white").save(stream, format="PNG")
        document = call("POST", "/me/documents", 201, content=stream.getvalue())
        draft = call("POST", f'/me/documents/{document["id"]}/transcription', 201, json={
            "values": [{"field": "weight_kg", "value": 70, "unit": "kg"}],
            "measured_on": (datetime.now(timezone.utc)-timedelta(days=1)).date().isoformat(),
            "device_id": "synthetic-bia", "device_model": "synthetic-device", "protocol_id": "synthetic-report-v1"})
        assert call("GET", "/me/observations")["total"] == 4
        reviewed = call("POST", f'/me/report-drafts/{draft["id"]}/confirm', 201, json={
            "version": draft["version"], "selected_fields": ["weight_kg"], "checked_original": True,
            "acknowledged_flags": draft["required_acknowledgements"]})
        assert reviewed["observations"][0]["provenance"] == "extracted"
        assert call("GET", "/me/observations")["total"] == 5
        exported = call("GET", "/me/export")
        assert exported["files"] and "password_hash" not in json.dumps(exported)
        call("DELETE", f'/me/documents/{document["id"]}', 204)
        assert call("GET", "/me/observations")["total"] == 4
    finally:
        if headers:
            call("DELETE", "/me/account", 204, json={"password": password})
            assert client.get("/api/v1/me/profile", headers=headers).status_code == 401

report = {"run_at": datetime.now(timezone.utc).isoformat(), "data": "fictional temporary account only",
          "steps_passed": len(steps), "cleanup": "temporary account and uploaded file deleted",
          "steps": steps, "limits": ["No real OCR/CV or clinical accuracy evaluation", "No native device UI automation"]}
if args.report:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
print(f"PASS: {len(steps)} HTTP steps; temporary account and files deleted")
