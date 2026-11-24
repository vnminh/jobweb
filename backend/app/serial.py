"""JSON shapes shared by the routers + cached taxonomy names."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import Session

from .db import SessionLocal
from .i18n import DEGREE_VI, GROUP_VI, JOB_TYPE_VI, SEN_VI, state_name
from .models import Job, OccGroup, Occupation, SeekerProfile, Skill


@lru_cache(maxsize=1)
def names() -> dict:
    db = SessionLocal()
    try:
        return {"occ": {o.key: o.name for o in db.query(Occupation)}, "occ_group_of": {o.key: o.group_key for o in db.query(Occupation)},
                "group": {g.key: g.name for g in db.query(OccGroup)}, "skill": {s.key: s.name for s in db.query(Skill)}}
    finally:
        db.close()


def iso(d):
    return d.isoformat() if d else None


def job_brief(j: Job) -> dict:
    n = names()
    return {"id": j.id, "title": j.title, "city": j.city, "state": j.state, "country": j.country, "job_type": j.job_type,
            "job_type_label": JOB_TYPE_VI.get(j.job_type or "", None), "seniority": j.seniority, "seniority_label": SEN_VI.get(j.seniority or ""),
            "state_name": state_name(j.state),
            "occupation_code": j.occupation_code, "occupation": n["occ"].get(j.occupation_code), "occ_group": j.occ_group,
            "occ_group_name": GROUP_VI.get(j.occ_group or "", n["group"].get(j.occ_group)), "start_date": iso(j.start_date), "end_date": iso(j.end_date),
            "status": j.status, "source": j.source, "company": j.company.name if j.company else None,
            "is_new": j.source == "web", "snippet": (j.description or "")[:220]}


def job_detail(j: Job) -> dict:
    n = names()
    d = job_brief(j)
    d.update(description=j.description, requirements=j.requirements, zip5=j.zip5, city_key=j.city_key, degree_req=j.degree_req,
             degree_req_label=DEGREE_VI[int(j.degree_req)] if j.degree_req is not None else None, years_req=j.years_req,
             salary_mentioned=bool(j.salary_mentioned), window_id=j.window_id, company_id=j.company_id,
             skills=[{"key": s.skill_key, "name": n["skill"].get(s.skill_key, s.skill_key)} for s in j.skills])
    return d


def seeker_out(p: SeekerProfile, with_history: bool = True) -> dict:
    n = names()
    d = {"id": p.id, "account_id": p.account_id, "full_name": p.account.full_name if p.account else None,
         "email": p.account.email if p.account else None, "dataset_user_id": p.dataset_user_id, "window_id": p.window_id,
         "split": p.split, "city": p.city, "city_key": p.city_key, "state": p.state, "country": p.country, "zip5": p.zip5, "degree_type": p.degree_type, "degree_label": DEGREE_VI[int(p.degree_ord or 0)], "state_name": state_name(p.state),
         "degree_ord": p.degree_ord, "major": p.major, "graduation_date": iso(p.graduation_date),
         "work_history_count": p.work_history_count, "total_years_experience": p.total_years_experience,
         "currently_employed": bool(p.currently_employed), "managed_others": bool(p.managed_others),
         "managed_how_many": p.managed_how_many, "last_occ": p.last_occ, "last_occ_name": n["occ"].get(p.last_occ),
         "seniority": p.seniority, "seniority_label": SEN_VI.get(p.seniority or ""), "has_embedding": p.world_idx is not None}
    if with_history:
        d["history"] = [{"sequence": h.sequence, "job_title": h.job_title, "occupation_code": h.occupation_code,
                         "occupation": n["occ"].get(h.occupation_code)} for h in p.history]
    return d


def seeker_engine_dict(db: Session, p: SeekerProfile) -> dict:
    """What the recommender needs about a seeker: embedding row, profile attributes, jobs already applied to."""
    from .models import Application

    hist = [w for (w,) in db.query(Job.world_idx).join(Application, Application.job_id == Job.id)
            .filter(Application.seeker_id == p.id, Job.world_idx.isnot(None))]
    return {"id": p.id, "dataset_user_id": p.dataset_user_id, "world_idx": p.world_idx, "state": p.state, "city_key": p.city_key,
            "last_occ": p.last_occ, "seniority": p.seniority, "history": hist, "years_exp": p.total_years_experience,
            "degree_ord": p.degree_ord, "history_occ": [h.occupation_code for h in p.history if h.occupation_code],
            # encoder inputs for web users (users.tsv / user_history.tsv fields)
            "titles": [h.job_title for h in p.history], "title_occ": [h.occupation_code for h in p.history],
            "currently_employed": bool(p.currently_employed), "managed_others": bool(p.managed_others),
            "managed_how_many": p.managed_how_many or 0, "major": p.major}


def job_engine_dict(j: Job) -> dict:
    """What the encoder / environment need about a job posted on the web."""
    return {"title": j.title, "description": j.description, "requirements": j.requirements, "occupation_code": j.occupation_code,
            "occ_group": j.occ_group, "skills": [s.skill_key for s in j.skills], "seniority": j.seniority, "job_type": j.job_type,
            "degree_req": j.degree_req, "city_key": j.city_key, "state": j.state}
