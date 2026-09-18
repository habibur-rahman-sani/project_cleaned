# from fastapi import APIRouter, HTTPException, Query

# from .. import auth, hermes_manager, repo

# router = APIRouter(prefix="/vtuber", tags=["vtuber"])


# @router.get("/resolve")
# async def resolve(token: str = Query(...)):
#     """
#     Open-LLM-VTuber ব্যাকএন্ড (patched — vtuber_patch/ দ্রষ্টব্য) প্রতিটা নতুন
#     websocket কানেকশনে এটা কল করে ওই ইউজারের Hermes এন্ডপয়েন্ট বের করে।
#     সেশন না থাকলে (ইউজার প্রথমবার কথা বলছে) নিজে থেকেই একটা চালু করে দেয়,
#     তাই ফ্রন্টএন্ডকে আলাদা করে /session/start কল করতে হয় না — শুধু ওয়েব UI
#     থেকে চাইলে দেখানোর জন্য /session/start আলাদা আছে (routes/sessions.py)।
#     """
#     user = await auth.get_user_from_raw_token(token)
#     if not user:
#         raise HTTPException(401, "অবৈধ টোকেন")

#     session = await hermes_manager.start_session(str(user["id"]))
#     return {
#         "user_id": str(user["id"]),
#         "base_url": session["base_url"],
#         "api_key": session["api_key"],
#     }


# @router.post("/touch")
# async def touch(token: str = Query(...)):
#     """প্রতিটা মেসেজের সময় VTuber ব্যাকএন্ড এটা কল করে last_active_at আপডেট
#     রাখে, যাতে idle reaper সক্রিয় ইউজারের প্রসেস বন্ধ করে না দেয়।"""
#     user = await auth.get_user_from_raw_token(token)
#     if not user:
#         raise HTTPException(401, "অবৈধ টোকেন")
#     existing = await repo.get_active_session(str(user["id"]))
#     if existing:
#         await hermes_manager.touch(str(existing["id"]))
#     return {"ok": True}

from fastapi import APIRouter, HTTPException, Query

from .. import auth, hermes_manager, repo

router = APIRouter(prefix="/vtuber", tags=["vtuber"])


@router.get("/resolve")
async def resolve(token: str = Query(...)):
    """
    Open-LLM-VTuber ব্যাকএন্ড (patched — vtuber_patch/ দ্রষ্টব্য) প্রতিটা নতুন
    websocket কানেকশনে এটা কল করে ওই ইউজারের Hermes এন্ডপয়েন্ট বের করে।
    সেশন না থাকলে (ইউজার প্রথমবার কথা বলছে) নিজে থেকেই একটা চালু করে দেয়,
    তাই ফ্রন্টএন্ডকে আলাদা করে /session/start কল করতে হয় না — শুধু ওয়েব UI
    থেকে চাইলে দেখানোর জন্য /session/start আলাদা আছে (routes/sessions.py)।

    start_session() এখন ভেতরে ভেতরে readiness-poll করে (হারমিস আসলেই পোর্টে
    bind করেছে কিনা) — তাই এখান থেকে base_url ফেরত মানে ওই এন্ডপয়েন্ট সত্যিই
    জীবিত। ব্যর্থ হলে (ক্র্যাশ/timeout) 503 দেওয়া হয়, যাতে vtuber ব্যাকএন্ড
    নীরবে একটা মৃত URL নিয়ে কাজ শুরু না করে এবং এরর সাথে সাথেই স্পষ্ট হয়।
    """
    user = await auth.get_user_from_raw_token(token)
    if not user:
        raise HTTPException(401, "অবৈধ টোকেন")

    try:
        session = await hermes_manager.start_session(str(user["id"]))
    except RuntimeError as e:
        raise HTTPException(503, f"Hermes সেশন রেডি করা যায়নি: {e}") from e

    return {
        "user_id": str(user["id"]),
        "base_url": session["base_url"],
        "api_key": session["api_key"],
    }


@router.post("/touch")
async def touch(token: str = Query(...)):
    """প্রতিটা মেসেজের সময় VTuber ব্যাকএন্ড এটা কল করে last_active_at আপডেট
    রাখে, যাতে idle reaper সক্রিয় ইউজারের প্রসেস বন্ধ করে না দেয়।"""
    user = await auth.get_user_from_raw_token(token)
    if not user:
        raise HTTPException(401, "অবৈধ টোকেন")
    existing = await repo.get_active_session(str(user["id"]))
    if existing:
        await hermes_manager.touch(str(existing["id"]))
    return {"ok": True}