import hashlib
import hmac
from enum import StrEnum
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from app.core.vault import signing_key
class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
hasher = PasswordHasher()
def hash_token(value):
    return hashlib.sha256(value.encode()).hexdigest()
def csrf_for(token):
    return hmac.new(signing_key(), ("csrf:" + token).encode(), hashlib.sha256).hexdigest()
def fingerprint(value):
    return hmac.new(signing_key(), ("login:" + value).encode(), hashlib.sha256).hexdigest()
def password_valid(encoded, password):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False
