from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..auth import optional_account, require
from ..db import get_db
from ..models import Account, Application, Job
from ..recsys.engine import get_engine
from ..serial import job_brief, job_detail

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def search(q: str = "", state: str = "", city: str = "", job_type: str = "", occ_group: str = "", seniority: str = "",
           page: int = 1, size: int = 20, db: Session = Depends(get_db)):
    qs = db.query(Job).options(joinedload(Job.company)).filter(Job.status == "open")
    if q:
        like = f"%{q.strip()}%"
        qs = qs.filter(or_(Job.title.ilike(like), Job.description.ilike(like)) if len(q) > 3 else Job.title.ilike(like))
    if state:
        qs = qs.filter(Job.state == state)
    if city:
        qs = qs.filter(Job.city.ilike(city))
    if job_type:
        qs = qs.filter(Job.job_type == job_type)
    if occ_group:
        qs = qs.filter(Job.occ_group == occ_group)
    if seniority:
        qs = qs.filter(Job.seniority == seniority)
    size = max(1, min(size, 50))
    total = qs.count()
    rows = qs.order_by(Job.source.desc(), Job.start_date.desc()).offset((max(page, 1) - 1) * size).limit(size).all()
    return {"total": total, "page": page, "size": size, "items": [job_brief(j) for j in rows]}


@router.get("/{job_id}/similar")
def similar(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        return []
    qs = db.query(Job).options(joinedload(Job.company)).filter(Job.status == "open", Job.id != j.id)
    rows = []
    if j.occupation_code:
        rows = qs.filter(Job.occupation_code == j.occupation_code, Job.state == j.state).limit(6).all()
    if len(rows) < 6 and j.occ_group:
        rows += qs.filter(Job.occ_group == j.occ_group, Job.state == j.state, Job.id.notin_([r.id for r in rows])).limit(6 - len(rows)).all()
    return [job_brief(r) for r in rows]


@router.get("/{job_id}")
def detail(job_id: int, db: Session = Depends(get_db), acc: Account | None = Depends(optional_account)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "Không tìm thấy tin tuyển dụng")
    d = job_detail(j)
    d["n_applicants"] = db.query(func.count(Application.id)).filter(Application.job_id == j.id).scalar()
    if acc and acc.role == "seeker" and acc.seeker:
        app = db.query(Application).filter_by(seeker_id=acc.seeker.id, job_id=j.id).first()
        d["applied"] = app is not None
        d["application_status"] = app.status if app else None
        e = get_engine()
        d["fit"] = e.fit_score(acc.seeker.world_idx, j.world_idx) if e else None
    return d


@router.post("/{job_id}/apply")
def apply(job_id: int, source: str = "web", db: Session = Depends(get_db), acc: Account = Depends(require("seeker"))):
    j = db.get(Job, job_id)
    if j is None or j.status != "open":
        raise HTTPException(400, "Tin tuyển dụng không còn nhận hồ sơ")
    if db.query(Application).filter_by(seeker_id=acc.seeker.id, job_id=job_id).first():
        raise HTTPException(400, "Bạn đã ứng tuyển việc này")
    app = Application(seeker_id=acc.seeker.id, job_id=job_id, window_id=j.window_id, application_date=datetime.now(),
                      status="submitted", source=source if source in ("web", "assistant") else "web")
    db.add(app)
    db.commit()
    return {"ok": True, "application_id": app.id}
