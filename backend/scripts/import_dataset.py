"""Build the demo SQLite database from the JobUNICORN processed data (CareerBuilder 2012, window 7).

    cd jobweb/backend && python -m scripts.import_dataset

Imports, for window 7 (the report's test window):
  users.tsv            -> accounts (role seeker) + seeker_profiles      (cleaned by P2: degree_ord, years_exp, lat/lon)
  user_history.tsv     -> work_history (+ O*NET code from the P3 title map)
  jobs.tsv             -> jobs (canonical jobs only, HTML-free text from P2, attributes from P3)
  apps.tsv             -> applications (mapped to canonical jobs, A_cut5 role kept)
  graph attribute nodes-> occupations, occ_groups, skills, states, cities
The dataset has no employers: one demo recruiter account per state owns that state's imported jobs.
Demo logins: admin@jobweb.demo / admin123, recruiter.<state>@jobweb.demo / demo123, user<UserID>@jobweb.demo / demo123.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import bcrypt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import scipy.sparse as sp

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import DATA_ROOT, DB_PATH, DEMO_WINDOW  # noqa: E402
from app.i18n import state_name  # noqa: E402

W = DEMO_WINDOW
D = DATA_ROOT
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    for ext in ("-wal", "-shm"):
        p = Path(str(DB_PATH) + ext)
        if p.exists():
            p.unlink()
    from app.db import Base, engine
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    con = engine.raw_connection()
    cur = con.cursor()

    def insert(table: str, df: pd.DataFrame):
        df = df.astype(object).where(pd.notna(df), None)
        cols = list(df.columns)
        cur.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [tuple(None if v is None else (v.to_pydatetime() if isinstance(v, pd.Timestamp) else v) for v in r)
                         for r in df.itertuples(index=False, name=None)])
        con.commit()
        log(f"{table}: {len(df):,} rows")

    gd = D / "processed" / "graph"
    # ---- taxonomies
    occg = pd.read_parquet(gd / "nodes_occ_group.parquet")
    insert("occ_groups", occg[["key", "name"]])
    occ = pd.read_parquet(gd / "nodes_occupation.parquet")
    e = pd.read_parquet(gd / "edges_occ_child_of.parquet")
    occ["group_key"] = occ["idx"].map(dict(zip(e.src, occg.set_index("idx").loc[e.dst, "key"])))
    insert("occupations", occ[["key", "name", "group_key"]])
    skills = pd.read_parquet(gd / "nodes_skill.parquet")
    insert("skills", skills[["key", "name"]])

    # ---- jobs (window W, canonical only)
    jobs = pd.read_parquet(D / "interim" / "jobs.parquet", filters=[("window", "==", W)],
                           columns=["job_id", "window", "title", "city", "state", "country", "zip5", "start_date", "end_date",
                                    "canonical_job_id", "lat", "lon", "city_key"])
    jobs = jobs[jobs.job_id == jobs.canonical_job_id].copy()
    txt = pq.read_table(D / "interim" / "jobs_text.parquet", filters=[("window", "==", W)], columns=["job_id", "desc_clean", "req_clean"]).to_pandas()
    jobs = jobs.merge(txt, on="job_id", how="left")
    jf = pd.read_parquet(D / "processed" / "attributes" / "job_fields.parquet", filters=[("window", "==", W)],
                         columns=["job_id", "years_req", "degree_req", "job_type", "seniority", "salary_mentioned"])
    jobs = jobs.merge(jf, on="job_id", how="left")
    nj = pd.read_parquet(gd / "nodes_job.parquet")
    jobs["world_idx"] = jobs.job_id.map(dict(zip(nj.key, nj.idx)))
    jobs = jobs[jobs.world_idx.notna()].copy()
    jobs["world_idx"] = jobs.world_idx.astype(int)
    occ_m = sp.load_npz(gd / "job_attr_occupation.npz").tocsr()
    r, c = occ_m.nonzero()
    job_occ = dict(zip(r, occ.key.to_numpy()[c]))
    jobs["occupation_code"] = jobs.world_idx.map(job_occ)
    jobs["occ_group"] = jobs.occupation_code.map(dict(zip(occ.key, occ.group_key)))
    log(f"jobs window {W}: {len(jobs):,} canonical")

    # ---- cities/states used in window W
    users = pd.read_parquet(D / "interim" / "users.parquet", filters=[("window", "==", W)])
    states = sorted(set(jobs.state.dropna()) | set(users.state.dropna()))
    states = [s for s in states if s and s.isalpha() and len(s) <= 3]
    insert("states", pd.DataFrame({"key": states}))
    cities = pd.read_parquet(gd / "nodes_city.parquet")
    used = set(jobs.city_key.dropna()) | set(users.city_key.dropna())
    cities = cities[cities.key.isin(used) & cities.state.isin(states)]
    insert("cities", cities[["key", "name", "state", "lat", "lon"]])

    # ---- accounts
    demo_hash = bcrypt.hashpw(b"demo123", bcrypt.gensalt(rounds=10)).decode()
    admin_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt(rounds=10)).decode()
    now = pd.Timestamp.now()
    acc = [{"id": 1, "email": "admin@jobweb.demo", "password_hash": admin_hash, "role": "admin", "full_name": "Quản trị viên", "active": 1, "created_at": now}]
    job_states = sorted(s for s in jobs.state.dropna().unique() if s in states)
    comp = []
    for k, s in enumerate(job_states):
        aid = 2 + k
        acc.append({"id": aid, "email": f"recruiter.{s.lower()}@jobweb.demo", "password_hash": demo_hash, "role": "recruiter",
                    "full_name": f"Nhà tuyển dụng tại {state_name(s)}", "active": 1, "created_at": now})
        comp.append({"id": k + 1, "account_id": aid, "name": f"Nhà tuyển dụng tại {state_name(s)}", "state": s,
                     "description": f"Tổng hợp các tin tuyển dụng tại bang {state_name(s)}."})
    comp_of_state = {c["state"]: c["id"] for c in comp}
    base = 2 + len(job_states)
    users = users.reset_index(drop=True)
    users["account_id"] = base + np.arange(len(users))
    acc += [{"id": int(a), "email": f"user{int(u)}@jobweb.demo", "password_hash": demo_hash, "role": "seeker",
             "full_name": f"Ứng viên #{int(u)}", "active": 1, "created_at": now} for a, u in zip(users.account_id, users.user_id)]
    insert("accounts", pd.DataFrame(acc))
    insert("companies", pd.DataFrame(comp))

    # ---- seekers
    nu = pd.read_parquet(gd / "nodes_user.parquet")
    uf = pd.read_parquet(D / "processed" / "attributes" / "user_fields.parquet", filters=[("window", "==", W)], columns=["user_id", "seniority", "last_occ"])
    users = users.merge(uf, on="user_id", how="left")
    sk = pd.DataFrame({
        "id": np.arange(1, len(users) + 1), "account_id": users.account_id, "dataset_user_id": users.user_id, "window_id": W,
        "split": users.split, "city": users.city, "city_key": users.city_key, "state": users.state, "country": users.country, "zip5": users.zip5,
        "degree_type": users.degree.fillna("None"), "degree_ord": users.degree_ord.fillna(0).astype(int), "major": users.major_raw,
        "graduation_date": users.graduation_date, "work_history_count": users.work_history_count.fillna(0).astype(int),
        "total_years_experience": users.years_exp, "currently_employed": users.currently_employed.fillna(False).astype(int),
        "managed_others": users.managed_others.fillna(False).astype(int), "managed_how_many": users.managed_how_many.fillna(0).astype(int),
        "lat": users.lat, "lon": users.lon, "last_occ": users.last_occ, "seniority": users.seniority,
        "world_idx": users.user_id.map(dict(zip(nu.key, nu.idx))),
    })
    insert("seeker_profiles", sk)
    seeker_of_user = dict(zip(users.user_id, sk.id))

    # ---- work history (+ O*NET code via the P3 title map)
    h = pd.read_parquet(D / "interim" / "user_history.parquet", filters=[("window", "==", W)], columns=["user_id", "seq", "title"])
    hk = pd.read_parquet(D / "processed" / "p3" / "hist_title_keys.parquet", filters=[("window", "==", W)])
    h = h.merge(hk[["user_id", "seq", "title_key"]], on=["user_id", "seq"], how="left")
    tm = pd.read_parquet(D / "processed" / "p3" / "title_occupation_map.parquet", columns=["title_key", "code_1", "score_1"])
    tm = tm[tm.score_1 >= 0.6]
    h["occupation_code"] = h.title_key.map(dict(zip(tm.title_key, tm.code_1)))
    insert("title_map", pd.DataFrame({"title_key": tm.title_key, "code": tm.code_1, "score": tm.score_1}).drop_duplicates("title_key"))
    h = h[h.title.notna() & (h.title.str.strip() != "")]
    insert("work_history", pd.DataFrame({"seeker_id": h.user_id.map(seeker_of_user), "sequence": h.seq, "job_title": h.title.str.slice(0, 200),
                                         "occupation_code": h.occupation_code}))

    # ---- jobs table
    jdf = pd.DataFrame({
        "id": jobs.job_id, "window_id": W, "company_id": jobs.state.map(comp_of_state), "title": jobs.title.fillna("(không tiêu đề)").str.slice(0, 300),
        "description": jobs.desc_clean, "requirements": jobs.req_clean, "city": jobs.city, "city_key": jobs.city_key, "state": jobs.state, "country": jobs.country,
        "zip5": jobs.zip5, "start_date": jobs.start_date, "end_date": jobs.end_date, "lat": jobs.lat, "lon": jobs.lon,
        "occupation_code": jobs.occupation_code, "occ_group": jobs.occ_group, "job_type": jobs.job_type, "seniority": jobs.seniority,
        "degree_req": jobs.degree_req, "years_req": jobs.years_req, "salary_mentioned": jobs.salary_mentioned.fillna(False).astype(int),
        "status": "open", "source": "dataset", "world_idx": jobs.world_idx, "created_at": jobs.start_date,
    })
    insert("jobs", jdf)
    skm = sp.load_npz(gd / "job_attr_skill.npz").tocsr()
    sub = skm[jobs.world_idx.to_numpy()]
    r, c = sub.nonzero()
    insert("job_skills", pd.DataFrame({"job_id": jobs.job_id.to_numpy()[r], "skill_key": skills.key.to_numpy()[c]}).drop_duplicates())

    # ---- applications
    a = pd.read_parquet(D / "interim" / "apps.parquet", filters=[("window", "==", W)], columns=["user_id", "canonical_job_id", "app_date", "role"])
    a = a[a.canonical_job_id.isin(set(jobs.job_id)) & a.user_id.isin(seeker_of_user.keys())]
    a = a.sort_values("app_date").drop_duplicates(["user_id", "canonical_job_id"])
    insert("applications", pd.DataFrame({"seeker_id": a.user_id.map(seeker_of_user), "job_id": a.canonical_job_id, "window_id": W,
                                         "application_date": a.app_date, "status": "submitted", "source": "dataset",
                                         "dataset_role": a.role.where(a.role.isin(["history", "target"]), None)}))
    con.close()
    log(f"done -> {DB_PATH} ({DB_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
