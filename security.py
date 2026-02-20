from datetime import datetime, timedelta
import os

from jose import jwt, JWTError
from passlib.context import CryptContext

from settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, minutes: int = 60 * 24 * 7) -> str:
    expire = datetime.utcnow() + timedelta(minutes=minutes)
    to_encode = {"sub": subject, "exp": expire}
    secret = os.getenv("SECRET_KEY", settings.secret_key)
    return jwt.encode(to_encode, secret, algorithm=ALGORITHM)


def decode_token(token: str):
    secret = os.getenv("SECRET_KEY", settings.secret_key)
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM])
    except JWTError:
        return None
