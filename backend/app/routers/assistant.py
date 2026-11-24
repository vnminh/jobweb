"""Conversational job assistant = JobUNICORN environment + R3 policy (see recsys/engine.py)."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from ..auth import require
from ..db import get_db
from ..models import Account, Conversation, Job, State
from ..recsys.engine import get_engine
from ..serial import job_brief, seeker_engine_dict

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AnswerIn(BaseModel):
    answer: str | int | list[int] | None = None  # yes|no|whatever, [attr ids], [lo, hi], state attr id, rank (1-based), null


def _hydrate(db: Session, e, q: dict) -> dict:
    if q.get("type") == "rec":
        idx = q["jobs"]
        jobs = {j.world_idx: j for j in db.query(Job).options(joinedload(Job.company)).filter(Job.world_idx.in_(idx))}
        q["jobs"] = [dict(job_brief(jobs[i]), rank=k + 1) for k, i in enumerate(idx) if i in jobs]
    if q.get("type") == "confirm":
        states = [s.key for s in db.query(State).order_by(State.key)]
        from ..i18n import state_name

        q["state_options"] = [{"id": e.attr("state", s), "name": s, "label": state_name(s)} for s in states if e.attr("state", s) is not None]
    return q


def _save(db: Session, c, q: dict):
    env = c.env
    conv = db.get(Conversation, c.db_id) if c.db_id else None
    if conv is None:
        conv = Conversation(seeker_id=c.seeker_id)
        db.add(conv)
    conv.turns = env.t
    conv.n_questions = sum(1 for h in env.history if h["action"][0] != "rec")
    conv.success = env.success_turn is not None
    conv.success_turn = env.success_turn
    if conv.success:
        L = env.history[-1].get("list", [])
        j = db.query(Job).filter(Job.world_idx == L[env.success_rank - 1]).first() if L else None
        conv.accepted_job_id = j.id if j else None
    conv.transcript = json.dumps(c.turns, ensure_ascii=False, default=str)
    db.commit()
    c.db_id = conv.id
    return conv


@router.post("/start")
def start(db: Session = Depends(get_db), acc: Account = Depends(require("seeker"))):
    e = get_engine()
    if e is None:
        raise HTTPException(503, "Trợ lý đang khởi động, vui lòng thử lại sau ít phút")
    p = acc.seeker
    if p.world_idx is None:
        raise HTTPException(400, "Hãy hoàn thiện hồ sơ (kinh nghiệm làm việc, nơi ở) trước khi trò chuyện với trợ lý")
    c, q = e.start(seeker_engine_dict(db, p))
    _save(db, c, q)
    return {"conv_id": c.id, "step": _hydrate(db, e, q)}


@router.post("/{conv_id}/answer")
def answer(conv_id: str, body: AnswerIn, db: Session = Depends(get_db), acc: Account = Depends(require("seeker"))):
    e = get_engine()
    if e is None or conv_id not in e.convs:
        raise HTTPException(404, "Phiên hội thoại đã hết hạn, hãy bắt đầu lại")
    c = e.convs[conv_id]
    if c.seeker_id != acc.seeker.id:
        raise HTTPException(403, "Không phải phiên của bạn")
    c, q = e.answer(conv_id, body.answer)
    conv = _save(db, c, q)
    out = _hydrate(db, e, q)
    if q.get("done"):
        out["accepted_job"] = job_brief(db.get(Job, conv.accepted_job_id)) if conv.accepted_job_id else None
        out["n_questions"] = conv.n_questions
    return {"conv_id": conv_id, "step": out}
