from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings
from . import repo

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[str]:
    """টোকেন ভ্যালিড হলে user_id (str) রিটার্ন করে, নাহলে None।"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """
    সব প্রোটেক্টেড রাউটে এই dependency ব্যবহার হয় — Authorization: Bearer <jwt>
    হেডার থেকে ইউজার বের করে। VTuber ব্যাকএন্ড websocket-এ header পাঠাতে পারে না
    বলে সেখানে token ?token=... query param দিয়েও পাঠানো যায় (routes/vtuber.py দেখো)।
    """
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authorization টোকেন নেই")
    user_id = decode_token(creds.credentials)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "টোকেন অবৈধ বা মেয়াদ শেষ")
    user = await repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ইউজার পাওয়া যায়নি")
    return user


async def get_user_from_raw_token(token: str):
    """query-param টোকেন (websocket/HTTP উভয় জায়গায় ব্যবহারের জন্য হেল্পার)।"""
    user_id = decode_token(token)
    if not user_id:
        return None
    return await repo.get_user_by_id(user_id)
