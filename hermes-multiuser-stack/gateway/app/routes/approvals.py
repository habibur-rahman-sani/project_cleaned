"""
নতুন ফাইল: hermes-multiuser-stack/gateway/app/routes/approvals.py

এই ফাইলটাই Hermes Agent (সার্ভারে) আর চ্যাট UI (ইউজারের ব্রাউজারে)-এর মধ্যে
"অনুমতি চাই" বার্তা আদান-প্রদান করে।

ফ্লো:
1. Hermes Agent কোনো ঝুঁকিপূর্ণ কাজ (terminal command, computer_use action)
   করার আগে POST /approvals কল করে — এই কলটা ব্লক হয়ে থাকে (asyncio.Event
   দিয়ে) যতক্ষণ না ইউজার উত্তর দেয়, বা ১২০ সেকেন্ড টাইমআউট হয়।
2. চ্যাট UI প্রতি ২ সেকেন্ডে GET /approvals/pending পোল করে — pending
   কিছু থাকলে সেটা modal/popup আকারে দেখায় (৪টা বোতাম)।
3. ইউজার বোতাম চাপলে UI POST /approvals/{id}/respond কল করে — এটাই
   ধাপ ১-এর ব্লক হয়ে থাকা কলকে জাগিয়ে দেয়, উত্তরসহ।

মেমোরিতে রাখা হচ্ছে (DB না) কারণ approval request-গুলো সেকেন্ডের হিসেবে
বাঁচে — persist করার দরকার নেই।
"""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth

router = APIRouter(prefix="/approvals", tags=["approvals"])


class _PendingApproval:
    def __init__(self, user_id: str, action: str, summary: str):
        self.id = uuid.uuid4().hex[:12]
        self.user_id = user_id
        self.action = action
        self.summary = summary
        self.created_at = time.time()
        self.decision: Optional[str] = None
        self.event = asyncio.Event()


# user_id -> list of pending approvals (সাধারণত একটাই একসময়ে, কিন্তু list
# রাখা হলো যাতে ভুলবশত দুটো একসাথে এলেও crash না করে)
_pending: Dict[str, list] = {}
_by_id: Dict[str, _PendingApproval] = {}


class ApprovalRequestBody(BaseModel):
    action: str
    summary: str


class ApprovalRespondBody(BaseModel):
    # "approve_once" | "approve_session" | "always_approve" | "deny"
    decision: str


# ---------------- Hermes Agent (সার্ভার) থেকে কল হয় ----------------
# Authorization header-এ HERMES_RELAY_TOKEN যায় — এটাই সেই ইউজারের নিজস্ব
# JWT (hermes_manager.py প্রতিটা প্রোফাইল স্পন করার সময় এই একই টোকেন বসায়),
# তাই get_current_user দিয়েই সঠিক user_id বের হয়ে যায় — আলাদা কোনো নতুন
# পরিচয়-যাচাই ব্যবস্থা বানাতে হয়নি।

@router.post("")
async def create_approval(body: ApprovalRequestBody, user=Depends(auth.get_current_user)):
    user_id = str(user["id"])
    pending = _PendingApproval(user_id, body.action, body.summary)
    _pending.setdefault(user_id, []).append(pending)
    _by_id[pending.id] = pending

    try:
        # সর্বোচ্চ ১২০ সেকেন্ড অপেক্ষা — ইউজার চ্যাটে বোতাম না চাপলে timeout
        await asyncio.wait_for(pending.event.wait(), timeout=120.0)
        return {"decision": pending.decision or "timeout"}
    except asyncio.TimeoutError:
        return {"decision": "timeout"}
    finally:
        _pending.get(user_id, []).remove(pending) if pending in _pending.get(user_id, []) else None
        _by_id.pop(pending.id, None)


# ---------------- চ্যাট UI (ব্রাউজার) থেকে কল হয় ----------------
# এখানে normal user JWT যায় (লগইনের সময় পাওয়া টোকেন), get_current_user
# দিয়েই user_id বের হয় — তাই একজন ইউজার শুধু নিজের pending approval-ই
# দেখতে/উত্তর দিতে পারবে, অন্য কারোটা না।

@router.get("/pending")
async def get_pending(user=Depends(auth.get_current_user)):
    user_id = str(user["id"])
    items = _pending.get(user_id, [])
    return {
        "pending": [
            {"id": p.id, "action": p.action, "summary": p.summary, "created_at": p.created_at}
            for p in items
        ]
    }


@router.post("/{approval_id}/respond")
async def respond(approval_id: str, body: ApprovalRespondBody, user=Depends(auth.get_current_user)):
    pending = _by_id.get(approval_id)
    if pending is None:
        raise HTTPException(404, "এই approval request আর নেই (হয়তো টাইমআউট হয়ে গেছে)")
    if pending.user_id != str(user["id"]):
        raise HTTPException(403, "এটা তোমার approval request না")
    if body.decision not in ("approve_once", "approve_session", "always_approve", "deny"):
        raise HTTPException(400, "decision হতে হবে: approve_once | approve_session | always_approve | deny")
    pending.decision = body.decision
    pending.event.set()  # POST /approvals-এ ব্লক হয়ে থাকা কলকে জাগিয়ে দিলো
    return {"ok": True}
