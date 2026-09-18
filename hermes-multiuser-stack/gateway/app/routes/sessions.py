from fastapi import APIRouter, Depends, HTTPException

from .. import auth, hermes_manager, repo

router = APIRouter(prefix="/session", tags=["session"])


@router.post("/start")
async def start(user=Depends(auth.get_current_user)):
    """ইউজার চ্যাট শুরু করলে ফ্রন্টএন্ড এটা কল করবে — নিজস্ব Hermes প্রসেস
    চালু (বা আগেরটাই থাকলে সেটা) রিটার্ন করে।"""
    try:
        return await hermes_manager.start_session(str(user["id"]))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@router.post("/stop")
async def stop(user=Depends(auth.get_current_user)):
    existing = await repo.get_active_session(str(user["id"]))
    if not existing:
        return {"status": "already_stopped"}
    await hermes_manager.stop_session(str(existing["id"]))
    return {"status": "stopped"}


@router.get("/status")
async def status(user=Depends(auth.get_current_user)):
    existing = await repo.get_active_session(str(user["id"]))
    if not existing:
        return {"status": "stopped"}
    return {
        "status": existing["status"],
        "started_at": existing["started_at"].isoformat(),
        "last_active_at": existing["last_active_at"].isoformat(),
    }
