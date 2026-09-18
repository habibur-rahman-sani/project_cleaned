from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import auth, repo, crypto
from ..config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8)
    email: Optional[str] = None


class LoginBody(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


@router.post("/register", response_model=TokenOut)
async def register(body: RegisterBody):
    existing = await repo.get_user_by_username(body.username)
    if existing:
        raise HTTPException(400, "এই username আগে থেকেই আছে")
    password_hash = auth.hash_password(body.password)
    user = await repo.create_user(body.username, password_hash, body.email)
    token = auth.create_access_token(str(user["id"]))
    return TokenOut(access_token=token, user_id=str(user["id"]), username=user["username"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginBody):
    user = await repo.get_user_by_username(body.username)
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "ভুল username অথবা password")
    token = auth.create_access_token(str(user["id"]))
    return TokenOut(access_token=token, user_id=str(user["id"]), username=user["username"])


@router.get("/me")
async def me(user=Depends(auth.get_current_user)):
    return {"id": str(user["id"]), "username": user["username"], "email": user["email"]}


# ---------- LLM key config: নিজের key দিবে, নাকি শেয়ার্ড OpenRouter ----------

class LLMConfigBody(BaseModel):
    provider: Literal["own_key", "openrouter_shared"]
    api_key: Optional[str] = None      # provider == own_key হলে required
    base_url: Optional[str] = None     # own_key কাস্টম এন্ডপয়েন্ট হলে (না দিলে OpenRouter ধরা হয়)
    model_name: Optional[str] = None


@router.put("/llm-config")
async def set_llm_config(body: LLMConfigBody, user=Depends(auth.get_current_user)):
    if body.provider == "own_key" and not body.api_key:
        raise HTTPException(400, "own_key বাছলে api_key দিতে হবে")

    encrypted = crypto.encrypt(body.api_key) if body.api_key else None
    model_name = body.model_name or (
        settings.shared_openrouter_model if body.provider == "openrouter_shared" else "openrouter/auto"
    )
    base_url = body.base_url or (
        settings.shared_openrouter_base_url if body.provider == "openrouter_shared" else None
    )
    row = await repo.upsert_llm_config(
        user_id=str(user["id"]), provider=body.provider,
        api_key_encrypted=encrypted, base_url=base_url, model_name=model_name,
    )
    return {
        "provider": row["provider"],
        "model_name": row["model_name"],
        "base_url": row["base_url"],
        "has_own_key": row["api_key_encrypted"] is not None,
    }


@router.get("/llm-config")
async def get_llm_config(user=Depends(auth.get_current_user)):
    row = await repo.get_llm_config(str(user["id"]))
    if not row:
        return {
            "provider": "openrouter_shared",
            "model_name": settings.shared_openrouter_model,
            "base_url": settings.shared_openrouter_base_url,
            "has_own_key": False,
        }
    return {
        "provider": row["provider"],
        "model_name": row["model_name"],
        "base_url": row["base_url"],
        "has_own_key": row["api_key_encrypted"] is not None,
    }
