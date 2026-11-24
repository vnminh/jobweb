"""Taxonomies (dropdown values = the attribute nodes of the JobUNICORN graph) and pipeline helpers for forms."""

import re
import sys

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import REPO
from ..db import get_db
from ..i18n import DEGREE_VI, GROUP_VI, JOB_TYPE_VI, SEN_VI, state_name
from ..models import SENIORITY, Account, City, Company, Job, OccGroup, Occupation, Skill, State, TitleMap
from ..recsys.engine import engine_error, get_engine

router = APIRouter(prefix="/api/meta", tags=["meta"])
sys.path.insert(0, str(REPO / "src"))


@router.get("/taxonomy")
def taxonomy(db: Session = Depends(get_db)):
    return {
        "occ_groups": sorted([{"key": g.key, "name": GROUP_VI.get(g.key, g.name)} for g in db.query(OccGroup)], key=lambda x: x["name"]),
        "occupations": [{"key": o.key, "name": o.name, "group_key": o.group_key} for o in db.query(Occupation).order_by(Occupation.name)],
        "skills": [{"key": s.key, "name": s.name} for s in db.query(Skill).order_by(Skill.name)],
        "states": [s.key for s in db.query(State).order_by(State.key)],
        "state_names": {s.key: state_name(s.key) for s in db.query(State)},
        "job_types": [{"key": k, "name": v} for k, v in JOB_TYPE_VI.items()],
        "seniority": SENIORITY,
        "seniority_names": SEN_VI,
        "degrees": [{"ord": i, "name": n} for i, n in enumerate(DEGREE_VI)],
    }


@router.get("/stats")
def public_stats(db: Session = Depends(get_db)):
    from sqlalchemy import func

    open_jobs = db.query(func.count(Job.id)).filter(Job.status == "open").scalar()
    companies = db.query(func.count(func.distinct(Job.company_id))).filter(Job.status == "open").scalar()
    seekers = db.query(func.count(Account.id)).filter(Account.role == "seeker", Account.active.is_(True)).scalar()
    groups = [{"key": k, "name": GROUP_VI.get(k, k), "jobs": n} for k, n in db.query(Job.occ_group, func.count(Job.id))
              .filter(Job.status == "open", Job.occ_group.isnot(None)).group_by(Job.occ_group).order_by(func.count(Job.id).desc())]
    states = [{"key": k, "name": state_name(k), "jobs": n} for k, n in db.query(Job.state, func.count(Job.id))
              .filter(Job.status == "open").group_by(Job.state).order_by(func.count(Job.id).desc()).limit(12)]
    return {"open_jobs": open_jobs, "companies": companies, "seekers": seekers, "groups": groups, "states": states}


@router.get("/cities")
def cities(state: str, db: Session = Depends(get_db)):
    return [{"key": c.key, "name": c.name} for c in db.query(City).filter(City.state == state).order_by(City.name)]


def map_title(db: Session, title: str) -> tuple[str | None, float | None]:
    """P3 title -> O*NET mapping (lookup of the cleaned title in the precomputed map)."""
    from jobunicorn.attributes.occupation import clean_title_for_mapping

    key = clean_title_for_mapping(title or "")
    if not key:
        return None, None
    row = db.get(TitleMap, key)
    return (row.code, row.score) if row else (None, None)


@router.get("/suggest")
def suggest(title: str = "", text: str = "", db: Session = Depends(get_db)):
    """Suggest the structured attributes of a job posting from its title and text with the P3 extractors."""
    from jobunicorn.attributes.fields import job_seniority, job_types, mentions_salary, primary_job_type, required_degree, required_years

    code, score = map_title(db, title)
    occ = db.get(Occupation, code) if code else None
    years = required_years(text) if text else None
    sen, _src = job_seniority(title, years)
    low = f" {(title + ' ' + text).lower()} "
    skills = [s for s in db.query(Skill) if re.search(r"(?<![a-z0-9])" + re.escape(s.name.lower()) + r"(?![a-z0-9])", low)]
    return {"occupation_code": code, "occupation": occ.name if occ else None, "occ_group": occ.group_key if occ else None, "score": score,
            "job_type": primary_job_type(job_types(text)) if text else None, "seniority": sen, "degree_req": required_degree(text) if text else None,
            "years_req": years, "salary_mentioned": mentions_salary(text) if text else False,
            "skills": [{"key": s.key, "name": s.name} for s in skills[:15]]}


@router.get("/samples")
def samples(db: Session = Depends(get_db)):
    """Ready-made seeker profiles and job postings for creating test data."""
    from ..samples import resolved

    return resolved(db)


@router.get("/occupations/search")
def occ_search(q: str = Query("", min_length=0), db: Session = Depends(get_db)):
    qs = db.query(Occupation)
    if q:
        qs = qs.filter(Occupation.name.ilike(f"%{q}%"))
    return [{"key": o.key, "name": o.name, "group_key": o.group_key} for o in qs.order_by(Occupation.name).limit(30)]


@router.get("/engine")
def engine_status():
    e = get_engine()
    return {"loaded": e is not None, "error": engine_error(), "load_sec": getattr(e, "load_sec", None),
            "model": {"name": "JobUNICORN R3 (Double DQN, R-GCN state graph)", "belief": "softmax, T_b = 1.758",
                      "val": {"SR@15": 0.898, "hDCG": 0.441}, "test": {"SR@15": 0.873, "hDCG": 0.413, "AT": 6.29}}}
