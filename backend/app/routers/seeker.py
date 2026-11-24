from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from ..auth import require
from ..db import get_db
from ..models import DEGREES, Account, Application, City, Job, WorkHistory
from ..recsys.engine import get_engine
from ..serial import iso, job_brief, seeker_engine_dict, seeker_out
from .meta import map_title

router = APIRouter(prefix="/api/seeker", tags=["seeker"])


class HistoryIn(BaseModel):
    job_title: str = Field(min_length=1, max_length=200)


class ProfileIn(BaseModel):
    full_name: str | None = None
    city_key: str | None = None
    state: str | None = None
    zip5: str | None = None
    degree_ord: int = Field(0, ge=0, le=6)
    major: str | None = None
    graduation_date: str | None = None
    total_years_experience: float | None = Field(None, ge=0, le=50)
    currently_employed: bool = False
    managed_others: bool = False
    managed_how_many: int = Field(0, ge=0)
    last_occ: str | None = None
    history: list[HistoryIn] = []


def _seniority(years, managed, last_title):
    from jobunicorn.attributes.fields import user_seniority  # P3 rule

    try:
        return user_seniority(years, managed, last_title)
    except Exception:
        return None


@router.get("/profile")
def get_profile(acc: Account = Depends(require("seeker"))):
    return seeker_out(acc.seeker)


@router.put("/profile")
def put_profile(body: ProfileIn, db: Session = Depends(get_db), acc: Account = Depends(require("seeker"))):
    p = acc.seeker
    if body.full_name:
        acc.full_name = body.full_name.strip()
    if body.city_key:
        c = db.get(City, body.city_key)
        if c:
            p.city, p.city_key, p.state = c.name, c.key, c.state
    elif body.state:
        p.state, p.city, p.city_key = body.state, None, None
    p.zip5 = body.zip5
    p.degree_ord, p.degree_type = body.degree_ord, DEGREES[body.degree_ord]
    p.major = body.major
    p.graduation_date = datetime.fromisoformat(body.graduation_date) if body.graduation_date else None
    p.total_years_experience = body.total_years_experience
    p.currently_employed, p.managed_others, p.managed_how_many = body.currently_employed, body.managed_others, body.managed_how_many
    # user_history.tsv: Sequence 1 = most recent; map each title to O*NET with the P3 title map
    p.history.clear()
    db.flush()
    for k, h in enumerate(body.history, start=1):
        code, _ = map_title(db, h.job_title)
        p.history.append(WorkHistory(sequence=k, job_title=h.job_title.strip(), occupation_code=code))
    p.work_history_count = len(body.history)
    p.last_occ = body.last_occ or next((h.occupation_code for h in p.history if h.occupation_code), None)
    p.seniority = _seniority(p.total_years_experience, p.managed_others, body.history[0].job_title if body.history else None)
    e = get_engine()
    if e is not None and (p.dataset_user_id is None):  # web user: (re)build the embedding row from the profile
        p.world_idx = e.register_user(seeker_engine_dict(db, p), p.world_idx)
    db.commit()
    db.refresh(p)
    return seeker_out(p)


@router.get("/applications")
def my_applications(db: Session = Depends(get_db), acc: Account = Depends(require("seeker"))):
    rows = (db.query(Application).options(joinedload(Application.job).joinedload(Job.company))
            .filter(Application.seeker_id == acc.seeker.id).order_by(Application.application_date.desc()).all())
    return [{"id": a.id, "status": a.status, "source": a.source, "dataset_role": a.dataset_role, "application_date": iso(a.application_date),
             "job": job_brief(a.job)} for a in rows]


@router.delete("/applications/{app_id}")
def withdraw(app_id: int, db: Session = Depends(get_db), acc: Account = Depends(require("seeker"))):
    a = db.get(Application, app_id)
    if a is None or a.seeker_id != acc.seeker.id:
        raise HTTPException(404, "Không tìm thấy đơn ứng tuyển")
    db.delete(a)
    db.commit()
    return {"ok": True}


@router.get("/recommendations")
def quick_recs(db: Session = Depends(get_db), acc: Account = Depends(require("seeker"))):
    e = get_engine()
    if e is None:
        raise HTTPException(503, "Hệ thống gợi ý đang khởi động, vui lòng thử lại sau ít phút")
    p = acc.seeker
    if p.world_idx is None:
        raise HTTPException(400, "Hãy hoàn thiện hồ sơ (kinh nghiệm làm việc, nơi ở) để nhận gợi ý việc làm")
    idx = e.quick_recommend(seeker_engine_dict(db, p), k=10)
    jobs = {j.world_idx: j for j in db.query(Job).filter(Job.world_idx.in_(idx))}
    return [job_brief(jobs[i]) for i in idx if i in jobs]
