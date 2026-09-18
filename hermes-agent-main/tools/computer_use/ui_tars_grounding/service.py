# -*- coding: utf-8 -*-
"""
ছোট্ট HTTP মাইক্রোসার্ভিস — grounding_client.py-কে wrap করে।
gateway/relay_backend.py (বা hermes-agent-এর vision_routing.py) থেকে সহজে
কল করার জন্য (POST /locate)।

চালানো:
    uvicorn service:app --host 0.0.0.0 --port 8643

এনভ ভ্যারিয়েবল: UI_TARS_API_BASE, UI_TARS_API_KEY, UI_TARS_MODEL
(grounding_client.py দ্রষ্টব্য)
"""
from __future__ import annotations

import base64

from fastapi import FastAPI
from pydantic import BaseModel

from grounding_client import UiTarsGroundingClient

app = FastAPI(title="UI-TARS Grounding Service")


class LocateRequest(BaseModel):
    instruction: str
    image_b64: str  # স্ক্রিনশট PNG, base64
    width: int
    height: int


class LocateResponse(BaseModel):
    ok: bool
    x: int = 0
    y: int = 0
    thought: str = ""
    message: str = ""


@app.post("/locate", response_model=LocateResponse)
def locate(req: LocateRequest) -> LocateResponse:
    client = UiTarsGroundingClient()
    png_bytes = base64.b64decode(req.image_b64)
    result = client.locate(png_bytes, req.instruction, req.width, req.height)
    return LocateResponse(ok=result.ok, x=result.x, y=result.y, thought=result.thought, message=result.message)


@app.get("/health")
def health() -> dict:
    return {"ok": True}
