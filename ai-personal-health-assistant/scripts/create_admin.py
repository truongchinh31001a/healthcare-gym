"""Create an admin explicitly; public registration can never select an admin role."""
import argparse, getpass, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))
from pydantic import TypeAdapter, EmailStr
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.security import hasher
from app.models import User
parser = argparse.ArgumentParser()
parser.add_argument("--email", required=True)
args = parser.parse_args()
email = str(TypeAdapter(EmailStr).validate_python(args.email)).lower()
password = getpass.getpass("New admin password (12+ chars): ")
if len(password) < 12 or len(password) > 128:
    raise SystemExit("Password must contain 12–128 characters")
if password != getpass.getpass("Repeat password: "):
    raise SystemExit("Passwords differ")
with SessionLocal() as db:
    if db.scalar(select(User).where(User.email == email)):
        raise SystemExit("Account already exists; no role or password was changed")
    db.add(User(email=email, password_hash=hasher.hash(password), role="admin"))
    db.commit()
print("Administrator created")
