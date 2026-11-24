"""JobWeb demo API.  Run:  cd jobweb/backend && uvicorn app.main:app --port 8000"""

import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (register tables)
from .config import FRONTEND_DIST, LOAD_ENGINE
from .db import Base, SessionLocal, engine
from .recsys import engine as rec
from .routers import admin, assistant, auth, jobs, meta, recruiter, seeker

Base.metadata.create_all(engine)
app = FastAPI(title="JobWeb – demo JobUNICORN", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth, meta, jobs, seeker, assistant, recruiter, admin):
    app.include_router(r.router)


def _load_and_sync():
    """Load the recommender, then restore what lives only in memory: rows of web jobs/users and closed jobs."""
    rec.load_engine()
    e = rec.get_engine()
    if e is None:
        return
    from .models import Job, SeekerProfile
    from .serial import job_engine_dict, seeker_engine_dict

    db = SessionLocal()
    try:
        web_jobs = db.query(Job).filter(Job.source == "web").all()
        used = [j.world_idx for j in web_jobs if j.world_idx is not None]
        e.next_job = max([e.nJ0 - 1] + used) + 1
        for j in web_jobs:
            j.world_idx = e.register_job(job_engine_dict(j), j.world_idx, reembed=False)
        for (w,) in db.query(Job.world_idx).filter(Job.status != "open", Job.world_idx.isnot(None)):
            e.set_closed(w, True)
        web_users = db.query(SeekerProfile).filter(SeekerProfile.dataset_user_id.is_(None)).all()
        used = [p.world_idx for p in web_users if p.world_idx is not None]
        e.next_user = max([e.nU0 - 1] + used) + 1
        for p in web_users:
            if p.world_idx is not None or p.last_occ or p.city_key:
                p.world_idx = e.register_user(seeker_engine_dict(db, p), p.world_idx, reembed=False)
        e._reembed()  # one encoder pass for all web jobs/users
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def startup():
    if LOAD_ENGINE:
        threading.Thread(target=_load_and_sync, daemon=True).start()


@app.get("/api/health")
def health():
    return {"ok": True, "engine": rec.get_engine() is not None, "engine_error": rec.engine_error()}


if FRONTEND_DIST.exists():  # serve the built React app (npm run build) from the same port
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = FRONTEND_DIST / path
        return FileResponse(f if path and f.is_file() else FRONTEND_DIST / "index.html")
