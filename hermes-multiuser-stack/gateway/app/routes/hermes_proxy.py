"""
Render (বা অন্য বাইরের হোস্ট) থেকে ইউজারের Hermes-এ পৌঁছানোর পথ।

সমস্যা: প্রতিটা ইউজারের Hermes gateway কনটেইনারের ভেতরে 127.0.0.1:<পোর্ট>-এ চলে,
বাইরে থেকে ধরা যায় না। সমাধান: gateway-র যে পাবলিক URL আছেই সেটাই দরজা হবে।
 vtuber ব্যাকএন্ড এখানে রিকোয়েস্ট পাঠায়:
     <GATEWAY পাবলিক URL>/hermes/<পোর্ট>/v1/chat/completions
 gateway সেটাকে ভেতরে http://127.0.0.1:<পোর্ট>/v1/chat/completions-এ পাঠিয়ে দেয়
 (streaming/SSE সহ) আর উত্তর ফেরত দেয়।

নিরাপত্তা: Authorization: Bearer <ওই সেশনের api_secret> না মিললে ঢুকতে দেয় না।
api_secret শুধু /vtuber/resolve (বৈধ ইউজার-টোকেন লাগে) থেকে পাওয়া যায়, প্রতি সেশনে
আলাদা। শুধু /v1/... পথ ও শুধু PORT_RANGE-এর ভেতরের সক্রিয় সেশনের পোর্টে যায়।
"""
import secrets

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from .. import repo
from ..config import settings

router = APIRouter(prefix="/hermes", tags=["hermes-proxy"])

_SKIP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
    "trailers", "transfer-encoding", "upgrade", "content-length", "content-encoding",
    "host", "accept-encoding",
}


@router.api_route("/{port}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(port: int, path: str, request: Request):
    if not (settings.port_range_start <= port < settings.port_range_end):
        raise HTTPException(404, "not found")
    if path != "v1" and not path.startswith("v1/"):
        raise HTTPException(404, "not found")

    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    session = await repo.get_active_session_by_port(port)
    if not session or not token or not secrets.compare_digest(token, session["api_secret"]):
        raise HTTPException(401, "অবৈধ api key")

    # চ্যাট চলছে — idle reaper যেন এই ইউজারের প্রসেস বন্ধ না করে দেয়
    await repo.touch_session(session["id"])

    headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_HEADERS}
    headers["accept-encoding"] = "identity"

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=600.0, write=60.0, pool=5.0)
    )
    try:
        upstream_req = client.build_request(
            request.method,
            f"http://127.0.0.1:{port}/{path}",
            headers=headers,
            params=request.query_params,
            content=await request.body(),
        )
        upstream = await client.send(upstream_req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(502, f"Hermes-এ পৌঁছানো যায়নি: {e}") from e

    async def _close() -> None:
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers={k: v for k, v in upstream.headers.items() if k.lower() not in _SKIP_HEADERS},
        background=BackgroundTask(_close),
    )
