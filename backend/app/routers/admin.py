import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session, joinedload

from ..auth import require
from ..db import get_db
from ..i18n import DEGREE_VI, GROUP_VI, state_name
from ..models import ROLES, Account, Application, Conversation, Job, OccGroup, SeekerProfile
from ..recsys.engine import get_engine
from ..serial import iso, job_brief, seeker_out
from .auth import account_out

router = APIRouter(prefix="/api/admin", tags=["admin"])
ADMIN = Depends(require("admin"))


class AccountPatch(BaseModel):
    active: bool | None = None
    role: str | None = None


class StatusIn(BaseModel):
    status: str


@router.get("/stats")
def stats(db: Session = Depends(get_db), _=ADMIN):
    roles = dict(db.query(Account.role, func.count(Account.id)).group_by(Account.role).all())
    jobs_status = dict(db.query(Job.status, func.count(Job.id)).group_by(Job.status).all())
    jobs_source = dict(db.query(Job.source, func.count(Job.id)).group_by(Job.source).all())
    apps_status = dict(db.query(Application.status, func.count(Application.id)).group_by(Application.status).all())
    apps_source = dict(db.query(Application.source, func.count(Application.id)).group_by(Application.source).all())
    gname = {g.key: g.name for g in db.query(OccGroup)}
    top_groups = [{"key": k, "name": GROUP_VI.get(k or "", gname.get(k, "Khác")), "jobs": n} for k, n in
                  db.query(Job.occ_group, func.count(Job.id)).filter(Job.status == "open").group_by(Job.occ_group).order_by(func.count(Job.id).desc()).limit(10)]
    top_states = [{"state": state_name(s), "jobs": n} for s, n in db.query(Job.state, func.count(Job.id)).group_by(Job.state).order_by(func.count(Job.id).desc()).limit(10)]
    per_day = [{"day": str(d), "n": n} for d, n in db.query(func.date(Application.application_date), func.count(Application.id))
               .filter(Application.source == "dataset").group_by(func.date(Application.application_date)).order_by(func.date(Application.application_date))]
    degrees = [{"degree": DEGREE_VI[int(d or 0)] if (d or 0) > 0 else "Chưa có bằng cấp", "n": n} for d, n in db.query(SeekerProfile.degree_ord, func.count(SeekerProfile.id))
               .group_by(SeekerProfile.degree_ord).order_by(func.count(SeekerProfile.id).desc())]
    conv = db.query(func.count(Conversation.id), func.avg(Conversation.turns), func.sum(case((Conversation.success, 1), else_=0)), func.avg(Conversation.n_questions)).filter(Conversation.turns > 0).one()
    e = get_engine()
    return {"accounts": roles, "jobs_status": jobs_status, "jobs_source": jobs_source, "apps_status": apps_status, "apps_source": apps_source,
            "top_groups": top_groups, "top_states": top_states, "apps_per_day": per_day, "degrees": degrees,
            "conversations": {"n": conv[0] or 0, "avg_turns": float(conv[1] or 0), "success": int(conv[2] or 0), "avg_questions": float(conv[3] or 0)},
            "engine": {"loaded": e is not None, "load_sec": getattr(e, "load_sec", None), "active_sessions": len(e.convs) if e else 0}}


@router.get("/accounts")
def accounts(q: str = "", role: str = "", page: int = 1, size: int = 25, db: Session = Depends(get_db), _=ADMIN):
    qs = db.query(Account).options(joinedload(Account.seeker), joinedload(Account.company))
    if q:
        qs = qs.filter(or_(Account.email.ilike(f"%{q}%"), Account.full_name.ilike(f"%{q}%")))
    if role:
        qs = qs.filter(Account.role == role)
    total = qs.count()
    rows = qs.order_by(Account.id).offset((max(page, 1) - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size,
            "items": [dict(account_out(a), created_at=iso(a.created_at), state=(a.seeker.state if a.seeker else a.company.state if a.company else None),
                           dataset_user_id=a.seeker.dataset_user_id if a.seeker else None) for a in rows]}


@router.get("/accounts/{acc_id}")
def account_detail(acc_id: int, db: Session = Depends(get_db), _=ADMIN):
    a = db.get(Account, acc_id)
    if a is None:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    d = account_out(a)
    if a.seeker:
        d["profile"] = seeker_out(a.seeker)
        d["n_applications"] = db.query(func.count(Application.id)).filter(Application.seeker_id == a.seeker.id).scalar()
    if a.company:
        d["n_jobs"] = db.query(func.count(Job.id)).filter(Job.company_id == a.company.id).scalar()
    return d


@router.patch("/accounts/{acc_id}")
def patch_account(acc_id: int, body: AccountPatch, db: Session = Depends(get_db), me: Account = ADMIN):
    a = db.get(Account, acc_id)
    if a is None:
        raise HTTPException(404, "Không tìm thấy tài khoản")
    if a.id == me.id:
        raise HTTPException(400, "Không thể tự thay đổi tài khoản quản trị của mình")
    if body.active is not None:
        a.active = body.active
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(400, "Vai trò không hợp lệ")
        if body.role != a.role and body.role != "admin":
            raise HTTPException(400, "Chỉ có thể nâng một tài khoản lên quản trị viên (hồ sơ ứng viên/công ty không chuyển đổi được)")
        a.role = body.role
    db.commit()
    return account_out(a)


@router.get("/jobs")
def jobs(q: str = "", status: str = "", source: str = "", page: int = 1, size: int = 25, db: Session = Depends(get_db), _=ADMIN):
    qs = db.query(Job).options(joinedload(Job.company))
    if q:
        qs = qs.filter(Job.title.ilike(f"%{q}%"))
    if status:
        qs = qs.filter(Job.status == status)
    if source:
        qs = qs.filter(Job.source == source)
    total = qs.count()
    rows = qs.order_by(Job.created_at.desc()).offset((max(page, 1) - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size, "items": [job_brief(j) for j in rows]}


@router.post("/jobs/{job_id}/status")
def job_status(job_id: int, body: StatusIn, db: Session = Depends(get_db), _=ADMIN):
    j = db.get(Job, job_id)
    if j is None or body.status not in ("open", "closed"):
        raise HTTPException(400, "Yêu cầu không hợp lệ")
    j.status = body.status
    e = get_engine()
    if e:
        e.set_closed(j.world_idx, j.status != "open")
    db.commit()
    return {"ok": True}


@router.get("/conversations")
def conversations(page: int = 1, size: int = 20, db: Session = Depends(get_db), _=ADMIN):
    qs = db.query(Conversation).options(joinedload(Conversation.seeker).joinedload(SeekerProfile.account)).filter(Conversation.turns > 0)
    total = qs.count()
    rows = qs.order_by(Conversation.started_at.desc()).offset((max(page, 1) - 1) * size).limit(size).all()
    return {"total": total, "items": [{"id": c.id, "started_at": iso(c.started_at), "seeker": c.seeker.account.full_name if c.seeker else None,
                                       "turns": c.turns, "n_questions": c.n_questions, "success": c.success, "success_turn": c.success_turn,
                                       "accepted_job_id": c.accepted_job_id, "transcript": json.loads(c.transcript or "[]")} for c in rows]}
