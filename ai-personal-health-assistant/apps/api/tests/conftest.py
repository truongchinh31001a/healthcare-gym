import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.config import settings
from app.core.database import Base, make_engine
from app.main import app
from app.shared.dependencies import get_db


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "vault")
    monkeypatch.setattr(settings, "encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "environment", "development")
    engine = make_engine("sqlite+pysqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    def db():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = db
    monkeypatch.setattr("app.main.engine", engine)
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()


PASSWORD = "Demo-password-2026!"


def register(client, email="person@example.com"):
    result = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD, "adult_attestation": True})
    assert result.status_code == 201, result.text
    result = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "client": "mobile"})
    assert result.status_code == 200, result.text
    return {"Authorization": "Bearer " + result.json()["access_token"]}, result.json()["user"]


def grant(client, headers, purpose="health_data_processing", granted=True):
    result = client.post("/api/v1/me/consents", headers=headers, json={"purpose": purpose, "granted": granted})
    assert result.status_code == 201, result.text
    return result.json()


def profile(client, headers, **changes):
    body = {"display_name": "Synthetic Adult", "birth_date": "1995-04-20", "height_cm": 170,
            "gender": "unspecified", "timezone": "Asia/Bangkok", "version": 0, **changes}
    return client.put("/api/v1/me/profile", headers=headers, json=body)


@pytest.fixture
def account(setup):
    client, factory = setup
    headers, user = register(client)
    grant(client, headers)
    assert profile(client, headers).status_code == 200
    return client, factory, headers, user
