from datetime import datetime

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..auth import require
from ..db import get_db
from ..models import APP_STATUS, Account, Application, City, Job, JobSkill, Occupation, SeekerProfile
from ..recsys.engine import get_engine
from ..serial import iso, job_brief, job_detail, seeker_out

router = APIRouter(prefix="/api/recruiter", tags=["recruiter"])


class CompanyIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    state: str | None = None
    description: str | None = None


class JobIn(BaseModel):  # jobs.tsv fields + P3 attributes
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=10)
    requirements: str | None = None
    city_key: str
    zip5: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    occupation_code: str | None = None
    job_type: str | None = None
    seniority: str | None = None
    degree_req: int | None = Field(None, ge=0, le=6)
    years_req: float | None = Field(None, ge=0, le=40)
    salary_mentioned: bool = False
    skills: list[str] = []


class StatusIn(BaseModel):
    status: str


class PersonaIn(BaseModel):  # a sample candidate profile (not saved as an account)
    label: str | None = None
    last_occ: str | None = None
    city_key: str
    total_years_experience: float | None = Field(None, ge=0, le=50)
    degree_ord: int | None = Field(None, ge=0, le=6)
    managed_others: bool = False
    title: str | None = None  # most recent job title (for the seniority rule)


class SimulateIn(BaseModel):
    n_candidates: int = Field(8, ge=0, le=30)
    include_applicants: bool = True
    personas: list[PersonaIn] = []


def _own_job(db: Session, acc: Account, job_id: int) -> Job:
    j = db.get(Job, job_id)
    if j is None or acc.company is None or j.company_id != acc.company.id:
        raise HTTPException(404, "Không tìm thấy tin tuyển dụng của bạn")
    return j


def _apply_fields(db: Session, j: Job, body: JobIn):
    c = db.get(City, body.city_key)
    if c is None:
        raise HTTPException(400, "Thành phố không hợp lệ")
    occ = db.get(Occupation, body.occupation_code) if body.occupation_code else None
    j.title, j.description, j.requirements = body.title.strip(), body.description, body.requirements
    j.city, j.city_key, j.state, j.country, j.zip5, j.lat, j.lon = c.name, c.key, c.state, "US", body.zip5, c.lat, c.lon
    j.start_date = datetime.fromisoformat(body.start_date) if body.start_date else datetime.now()
    j.end_date = datetime.fromisoformat(body.end_date) if body.end_date else None
    j.occupation_code, j.occ_group = (occ.key, occ.group_key) if occ else (None, None)
    j.job_type, j.seniority, j.degree_req, j.years_req, j.salary_mentioned = body.job_type, body.seniority, body.degree_req, body.years_req, body.salary_mentioned
    j.skills = [JobSkill(skill_key=k) for k in dict.fromkeys(body.skills)]


def _sync_engine(j: Job):
    e = get_engine()
    if e is None:
        return
    if j.source == "web":
        from ..serial import job_engine_dict

        j.world_idx = e.register_job(job_engine_dict(j), j.world_idx)
    e.set_closed(j.world_idx, j.status != "open")


@router.get("/company")
def get_company(acc: Account = Depends(require("recruiter"))):
    c = acc.company
    return {"id": c.id, "name": c.name, "state": c.state, "description": c.description}


@router.put("/company")
def put_company(body: CompanyIn, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    c = acc.company
    c.name, c.state, c.description = body.name, body.state, body.description
    db.commit()
    return {"id": c.id, "name": c.name, "state": c.state, "description": c.description}


@router.get("/stats")
def stats(db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    cid = acc.company.id
    n_open = db.query(func.count(Job.id)).filter(Job.company_id == cid, Job.status == "open").scalar()
    n_closed = db.query(func.count(Job.id)).filter(Job.company_id == cid, Job.status != "open").scalar()
    apps = dict(db.query(Application.status, func.count(Application.id)).join(Job).filter(Job.company_id == cid).group_by(Application.status).all())
    return {"open": n_open, "closed": n_closed, "applications": apps, "total_applications": sum(apps.values())}


@router.get("/jobs")
def my_jobs(q: str = "", status: str = "", page: int = 1, size: int = 20, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    qs = db.query(Job).filter(Job.company_id == acc.company.id)
    if q:
        qs = qs.filter(Job.title.ilike(f"%{q}%"))
    if status:
        qs = qs.filter(Job.status == status)
    total = qs.count()
    rows = qs.order_by(Job.created_at.desc()).offset((max(page, 1) - 1) * size).limit(size).all()
    counts = dict(db.query(Application.job_id, func.count(Application.id)).filter(Application.job_id.in_([j.id for j in rows])).group_by(Application.job_id).all())
    return {"total": total, "page": page, "size": size, "items": [dict(job_brief(j), n_applicants=counts.get(j.id, 0)) for j in rows]}


@router.post("/jobs")
def create_job(body: JobIn, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    new_id = (db.query(func.max(Job.id)).scalar() or 0) + 1
    j = Job(id=new_id, window_id=7, company_id=acc.company.id, status="open", source="web", created_at=datetime.now())
    _apply_fields(db, j, body)
    db.add(j)
    db.flush()
    _sync_engine(j)
    db.commit()
    return job_detail(j)


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    return job_detail(_own_job(db, acc, job_id))


@router.put("/jobs/{job_id}")
def update_job(job_id: int, body: JobIn, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    j = _own_job(db, acc, job_id)
    _apply_fields(db, j, body)
    db.flush()
    _sync_engine(j)
    db.commit()
    return job_detail(j)


@router.post("/jobs/{job_id}/status")
def set_status(job_id: int, body: StatusIn, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    if body.status not in ("open", "closed"):
        raise HTTPException(400, "Trạng thái không hợp lệ")
    j = _own_job(db, acc, job_id)
    j.status = body.status
    _sync_engine(j)
    db.commit()
    return {"ok": True, "status": j.status}


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    j = _own_job(db, acc, job_id)
    if db.query(Application).filter_by(job_id=j.id).count():
        raise HTTPException(400, "Tin đã có hồ sơ ứng tuyển — hãy đóng tin thay vì xoá")
    e = get_engine()
    if e:
        e.set_closed(j.world_idx, True)
    db.delete(j)
    db.commit()
    return {"ok": True}


@router.get("/jobs/{job_id}/applicants")
def applicants(job_id: int, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    j = _own_job(db, acc, job_id)
    e = get_engine()
    rows = (db.query(Application).options(joinedload(Application.seeker).joinedload(SeekerProfile.account), joinedload(Application.seeker).joinedload(SeekerProfile.history))
            .filter(Application.job_id == j.id).order_by(Application.application_date.desc()).all())
    out = []
    for a in rows:
        fit = e.fit_score(a.seeker.world_idx, j.world_idx) if e else None
        out.append({"id": a.id, "status": a.status, "source": a.source, "application_date": iso(a.application_date),
                    "seeker": seeker_out(a.seeker), "fit": fit})
    return {"job": job_brief(j), "items": out}


@router.put("/applications/{app_id}/status")
def app_status(app_id: int, body: StatusIn, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    a = db.get(Application, app_id)
    if a is None or a.job.company_id != acc.company.id:
        raise HTTPException(404, "Không tìm thấy hồ sơ")
    if body.status not in APP_STATUS:
        raise HTTPException(400, "Trạng thái không hợp lệ")
    a.status = body.status
    db.commit()
    return {"ok": True, "status": a.status}


@router.get("/jobs/{job_id}/suggested")
def suggested(job_id: int, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    """Seekers whose encoder embedding matches the job best (e_u . e_v), same state first; excludes current applicants."""
    j = _own_job(db, acc, job_id)
    e = get_engine()
    if e is None or j.world_idx is None:
        raise HTTPException(503, "Hệ thống gợi ý đang khởi động, vui lòng thử lại sau")
    applied = {s for (s,) in db.query(Application.seeker_id).filter(Application.job_id == j.id)}
    q = db.query(SeekerProfile.id, SeekerProfile.world_idx).filter(SeekerProfile.world_idx.isnot(None))
    pool = q.filter(SeekerProfile.state == j.state).all() if j.state else []
    if len(pool) < 30:
        pool = q.all()
    pool = [(sid, w) for sid, w in pool if sid not in applied]
    if not pool:
        return []
    rows = np.array([w for _, w in pool])
    sid_of = {w: sid for sid, w in pool}
    top = e.similar_users(j.world_idx, rows, k=15)
    profs = {p.id: p for p in db.query(SeekerProfile).options(joinedload(SeekerProfile.account), joinedload(SeekerProfile.history))
             .filter(SeekerProfile.id.in_([sid_of[w] for w, _ in top]))}
    return [dict(seeker=seeker_out(profs[sid_of[w]]), score=s, fit=e.fit_score(w, j.world_idx)) for w, s in top if sid_of[w] in profs]


@router.post("/jobs/{job_id}/simulate")
def simulate(job_id: int, body: SimulateIn, db: Session = Depends(get_db), acc: Account = Depends(require("recruiter"))):
    """Model test: would the JobUNICORN assistant (R3 policy) find this job for a seeker who wants exactly this job?
    The report's rule-based simulator answers the questions with this job as the only target."""
    from ..serial import seeker_engine_dict
    from .seeker import _seniority

    j = _own_job(db, acc, job_id)
    e = get_engine()
    if e is None or j.world_idx is None:
        raise HTTPException(503, "Hệ thống gợi ý đang khởi động, vui lòng thử lại sau")
    if j.status != "open":
        raise HTTPException(400, "Tin đang đóng — hãy mở lại tin để chạy mô phỏng")
    personas, kinds = [], []
    # 1) sample candidate profiles entered by the recruiter
    for k, p in enumerate(body.personas):
        c = db.get(City, p.city_key)
        if c is None:
            raise HTTPException(400, f"Thành phố không hợp lệ ở hồ sơ mẫu {k + 1}")
        occ = db.get(Occupation, p.last_occ) if p.last_occ else None
        personas.append({"label": p.label or f"Hồ sơ mẫu {k + 1}", "world_idx": None, "state": c.state, "city_key": c.key,
                         "last_occ": occ.key if occ else None, "history_occ": [occ.key] if occ else [],
                         "titles": [p.title] if p.title else [], "title_occ": [occ.key if occ else None] if p.title else [],
                         "seniority": _seniority(p.total_years_experience, p.managed_others, p.title),
                         "years_exp": p.total_years_experience, "degree_ord": p.degree_ord, "managed_others": p.managed_others,
                         "history": []})
        kinds.append("sample")
    # 2) real applicants of the job
    seen = set()
    if body.include_applicants:
        apps = db.query(Application).filter(Application.job_id == j.id).limit(10).all()
        for a in apps:
            if a.seeker.world_idx is not None:
                personas.append(dict(seeker_engine_dict(db, a.seeker), label=a.seeker.account.full_name))
                kinds.append("applicant")
                seen.add(a.seeker_id)
    # 3) seekers whose embedding matches the job best (same state first)
    if body.n_candidates:
        q = db.query(SeekerProfile.id, SeekerProfile.world_idx).filter(SeekerProfile.world_idx.isnot(None))
        pool = q.filter(SeekerProfile.state == j.state).all() if j.state else []
        if len(pool) < 30:
            pool = q.all()
        pool = [(sid, w) for sid, w in pool if sid not in seen]
        if pool:
            sid_of = {w: sid for sid, w in pool}
            for w, _s in e.similar_users(j.world_idx, np.array([w for _, w in pool]), k=body.n_candidates):
                sp = db.get(SeekerProfile, sid_of[w])
                personas.append(dict(seeker_engine_dict(db, sp), label=sp.account.full_name))
                kinds.append("candidate")
    if not personas:
        raise HTTPException(400, "Chưa có ứng viên nào để mô phỏng")
    res = e.simulate(j.world_idx, personas)
    titles = {}
    ids = {jj for r in res for t in r["turns"] for jj in t.get("jobs", [])}
    for row in db.query(Job.world_idx, Job.id, Job.title).filter(Job.world_idx.in_(list(ids))):
        titles[row[0]] = (row[1], row[2])
    for r, kind in zip(res, kinds):
        r["kind"] = kind
        for t in r["turns"]:
            if "jobs" in t:
                t["jobs"] = [{"id": titles.get(w, (None, "?"))[0], "title": titles.get(w, (None, "?"))[1], "is_target": w == j.world_idx} for w in t["jobs"]]
    found = [r for r in res if r["found"]]
    summary = {"n": len(res), "found": len(found), "success_rate": len(found) / len(res),
               "avg_turn": float(np.mean([r["turn"] for r in found])) if found else None,
               "avg_questions": float(np.mean([r["n_questions"] for r in res])),
               "reachable": sum(r["reachable"] for r in res)}
    return {"job": job_brief(j), "summary": summary, "results": res}
