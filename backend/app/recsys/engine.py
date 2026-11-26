"""Recommender service: the JobUNICORN conversational environment + the trained R3 DQN policy, driven by a real user.

The environment (`ConvEnv`) is exactly the one used in the report. The only change is the user: instead of the rule-based
simulator, `LiveUser` returns the answer the person clicked in the web UI. One web turn =
    env.step(pending_action) with the user's answer  ->  policy picks the next action  ->  sent to the browser.

New entities created on the web are embedded by the trained P5 encoder itself (GraphEncoder in encoder.py): the
R-GCN runs on the window-7 subgraph with the new job/user nodes attached through the same edge types and input
features as in the pipeline, so their vectors come from the same model as every dataset node.
The fit model g_phi only has features for dataset users/jobs; for web entities its term is 0 (documented limitation).
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field

import numpy as np
import scipy.sparse as sp

from ..config import DATA_ROOT, DEMO_WINDOW, EXTRA_JOBS, EXTRA_USERS, POLICY_PATH, REPO

YES, NO, WHATEVER = "yes", "no", "whatever"
TYPE_VI = {"occupation": "vị trí", "occ_group": "ngành nghề", "skill": "kỹ năng", "seniority": "cấp bậc", "job_type": "hình thức làm việc",
           "city": "thành phố", "state": "bang"}
from ..i18n import GROUP_VI, GROUP_VI_BY_NAME, JOB_TYPE_VI_BY_NAME, SEN_VI, state_name  # noqa: E402


class LiveUser:
    """Stands in for simulator.rule.UserSimulator: every method returns the answer given in the UI."""

    def __init__(self):
        self.targets = np.empty(0, dtype=np.int64)  # unknown for a real user (env only indexes with it)
        self.n: dict = {}
        self.answer = None

    def binary(self, a):
        return self.answer

    def choice(self, options):
        return self.answer

    def hier(self, parents):
        return self.answer

    def range(self, levels):
        return self.answer

    def confirm(self, state_attr, target_states):
        return self.answer

    def recommend(self, jobs):
        return self.answer  # 1-based rank of the accepted job, or None


class SafeFit:
    """g_phi for dataset users/jobs; 0 for entities created on the web (no fit features for them)."""

    def __init__(self, base, n_users: int, n_jobs: int):
        from jobunicorn.fit.scorer import FitScorer

        self.inner = FitScorer(base.data, base.model, base.scaler, base.base)
        self.nu, self.nj = n_users, n_jobs

    def score(self, sess, jobs):
        jobs = np.asarray(jobs)
        out = np.zeros(len(jobs))
        if int(sess["user_idx"]) >= self.nu:
            return out
        m = jobs < self.nj
        if m.any():
            out[m] = self.inner.score(sess, jobs[m])
        return out

    def unqualified_rate(self, sess, jobs):
        jobs = [j for j in jobs if j < self.nj]
        if int(sess["user_idx"]) >= self.nu or not jobs:
            return 0.0
        return self.inner.unqualified_rate(sess, jobs)


@dataclass
class Conv:
    id: str
    seeker_id: int
    env: object
    live: LiveUser
    pending: tuple | None = None
    pre: object = None
    turns: list = field(default_factory=list)
    created: float = field(default_factory=time.time)
    db_id: int | None = None


class Engine:
    def __init__(self):
        sys.path.insert(0, str(REPO / "src"))
        sys.path.insert(0, str(REPO / "scripts"))
        import torch

        import conv_run
        from jobunicorn.config import base_arg_parser, resolve_config
        from jobunicorn.env.conv_env import EnvConfig
        from jobunicorn.env.world import load_world
        from jobunicorn.fit.scorer import FitScorer
        from jobunicorn.policy.unicorn import DQNAgent, PolicyConfig

        t0 = time.time()
        self.lock = threading.RLock()
        cfg = resolve_config(base_arg_parser().parse_args(["--config", str(REPO / "configs" / "final.yaml"), "--data-root", str(DATA_ROOT)]))
        W = load_world(DATA_ROOT)
        self.nU0, self.nJ0, d = W.E_user.shape[0], W.E_job.shape[0], W.E_job.shape[1]
        # reserve rows for web users / jobs
        W.E_user = np.vstack([W.E_user, np.zeros((EXTRA_USERS, d), np.float32)])
        W.E_job = np.vstack([W.E_job, np.zeros((EXTRA_JOBS, d), np.float32)])
        self.A_base = W.A
        self.A_extra = sp.lil_matrix((EXTRA_JOBS, W.n_attr), dtype=W.A.dtype)
        W.A = sp.vstack([self.A_base, self.A_extra.tocsr()]).tocsr()
        W.AT = W.A.T.tocsr()
        pad = lambda x: np.concatenate([x, np.full(EXTRA_JOBS, -1, dtype=x.dtype)])
        W.job_window, W.job_state, W.job_city, W.job_seniority_ord, W.job_ids = map(pad, (W.job_window, W.job_state, W.job_city, W.job_seniority_ord, W.job_ids))
        self.W = W
        self.maps = conv_run.attr_maps(W, DATA_ROOT)
        wj = W.window_jobs[DEMO_WINDOW]
        self.job_norm = float(np.linalg.norm(W.E_job[wj], axis=1).mean())
        wu = self._window_users()
        self.user_norm = float(np.linalg.norm(W.E_user[wu], axis=1).mean()) if len(wu) else 1.0
        temp = json.loads((DATA_ROOT / "processed/sessions/score_temp.json").read_text())["score_temp"]
        env = dict(cfg["env"])
        env.update(belief="softmax", belief_temp=1.758, exclude_history=True, turn_penalty=0.08)
        self.envcfg = EnvConfig(**{**env, "score_temp": temp, "seed": 0})
        self.fit_base = FitScorer.load(DATA_ROOT, W, cfg["fit_model"])
        self.faiss_cache: dict = {}
        pol = dict(cfg.get("policy", {}))
        pol.update(use_state_feats=True, rec_order="w")
        self.pc = PolicyConfig(**pol)
        self.agent = DQNAgent(self.pc, torch.device("cpu"), total_steps=8, seed=0, tables=(W.E_user, W.E_attr, W.E_job))
        self.agent.q.load_state_dict(torch.load(POLICY_PATH, map_location="cpu"))
        self.agent.q.eval()
        self.next_user, self.next_job = self.nU0, self.nJ0
        self.closed: set[int] = set()  # world idx of closed / deleted jobs
        self.convs: dict[str, Conv] = {}
        # attribute lookup tables
        self.attr_key = {}
        import pandas as pd

        for t in W.types:
            n = pd.read_parquet(DATA_ROOT / "processed/graph" / f"nodes_{t}.parquet")
            for idx, key in zip(n["idx"], n["key"]):
                self.attr_key[(t, str(key))] = int(idx) + W.offset[t]
        # trained P5 encoder for entities created on the web (see encoder.py)
        from ..config import CACHE_DIR
        from .encoder import GraphEncoder

        self.enc = GraphEncoder(DATA_ROOT, REPO / "reports/p5_encoder/d_gnn_aux.pt", DEMO_WINDOW, CACHE_DIR)
        self.web_jobs: dict[int, dict] = {}  # world idx -> spec (title, text, attributes)
        self.web_users: dict[int, dict] = {}  # world idx -> profile spec
        self.scratch = list(range(self.nU0 + EXTRA_USERS - 20, self.nU0 + EXTRA_USERS))  # rows for test personas
        self.load_sec = time.time() - t0

    # ------------------------------------------------------------------ helpers
    def _window_users(self):
        import pandas as pd

        nu = pd.read_parquet(DATA_ROOT / "processed/graph/nodes_user.parquet", columns=["idx", "window"])
        return nu.idx[nu.window == DEMO_WINDOW].to_numpy()

    def attr(self, t: str, key) -> int | None:
        if key is None:
            return None
        return self.attr_key.get((t, str(key)))

    def attr_info(self, a: int) -> dict:
        t = self.W.type_of(a)
        name = self.W.attr_name[a].split(":", 1)[1]
        if t == "seniority":
            label = SEN_VI.get(name, name)
        elif t == "occ_group":
            label = GROUP_VI.get(GROUP_VI_BY_NAME.get(name, ""), name)
        elif t == "job_type":
            label = JOB_TYPE_VI_BY_NAME.get(name, name)
        elif t == "state":
            label = state_name(name)
        else:
            label = name
        return {"id": int(a), "type": t, "type_vi": TYPE_VI.get(t, t), "name": name, "label": label}

    def _reembed(self):
        """One forward pass of the trained encoder over window 7 + every web job/user; writes their rows only."""
        jids, uids = sorted(self.web_jobs), sorted(self.web_users)
        jv, uv = self.enc.embed([self.web_jobs[i] for i in jids], [self.web_users[i] for i in uids])
        for i, v in zip(jids, jv):
            self.W.E_job[i] = v
        for i, v in zip(uids, uv):
            self.W.E_user[i] = v
        self.faiss_cache.pop(DEMO_WINDOW, None)  # job vectors changed -> rebuild the window index on next query

    # ------------------------------------------------------------------ web entities
    def register_job(self, job: dict, world_idx: int | None = None, reembed: bool = True) -> int:
        """Create/update the world row of a job posted on the web. job: title, description, requirements,
        occupation_code, occ_group, skills (keys), seniority, job_type, degree_req, city_key, state. Returns the world idx."""
        W = self.W
        with self.lock:
            if world_idx is None:
                if self.next_job >= self.nJ0 + EXTRA_JOBS:
                    raise RuntimeError("no free job rows")
                world_idx = self.next_job
                self.next_job += 1
            r = world_idx - self.nJ0
            attrs = [self.attr("occupation", job.get("occupation_code")), self.attr("occ_group", job.get("occ_group")),
                     self.attr("seniority", job.get("seniority")), self.attr("job_type", job.get("job_type")),
                     self.attr("city", job.get("city_key")), self.attr("state", job.get("state"))]
            attrs += [self.attr("skill", s) for s in job.get("skills", [])]
            attrs = sorted({a for a in attrs if a is not None})
            self.A_extra[r, :] = 0
            for a in attrs:
                self.A_extra[r, a] = 1
            W.A = sp.vstack([self.A_base, self.A_extra.tocsr()]).tocsr()
            W.AT = W.A.T.tocsr()
            self.web_jobs[world_idx] = dict(job)
            if reembed:
                self._reembed()
            W.job_window[world_idx] = DEMO_WINDOW
            W.job_state[world_idx] = self.attr("state", job.get("state")) or -1
            W.job_city[world_idx] = self.attr("city", job.get("city_key")) or -1
            sen = job.get("seniority")
            W.job_seniority_ord[world_idx] = ["entry", "mid", "senior", "manager", "executive"].index(sen) if sen in SEN_VI else -1
            if world_idx not in set(W.window_jobs[DEMO_WINDOW].tolist()):
                W.window_jobs[DEMO_WINDOW] = np.append(W.window_jobs[DEMO_WINDOW], world_idx)
            self.faiss_cache.pop(DEMO_WINDOW, None)  # rebuild the FAISS index of the window on next query
            self.closed.discard(world_idx)
            return world_idx

    def set_closed(self, world_idx: int | None, closed: bool):
        if world_idx is None:
            return
        with self.lock:
            (self.closed.add if closed else self.closed.discard)(int(world_idx))

    def register_user(self, profile: dict, world_idx: int | None = None, reembed: bool = True) -> int:
        """Embedding row for a seeker who registered on the web, computed by the trained encoder from the profile
        (titles, title_occ, years_exp, degree_ord, currently_employed, managed_*, major, city_key, seniority, history)."""
        with self.lock:
            if world_idx is None:
                if self.next_user >= self.scratch[0]:  # last rows = scratch for test personas
                    raise RuntimeError("no free user rows")
                world_idx = self.next_user
                self.next_user += 1
            self.web_users[world_idx] = dict(profile, applied=list(profile.get("history", [])))
            if reembed:
                self._reembed()
            return world_idx

    # ------------------------------------------------------------------ conversation
    def _session(self, p: dict) -> dict:
        st = self.attr("state", p.get("state"))
        prof = [self.attr("occupation", p.get("last_occ")), self.attr("seniority", p.get("seniority")), self.attr("city", p.get("city_key")), st]
        return {"user_idx": int(p["world_idx"]), "user_id": p.get("dataset_user_id") or -1, "window": DEMO_WINDOW, "role": "web", "targets": [],
                "history": [int(j) for j in p.get("history", []) if j is not None], "state_attr": int(st) if st is not None else -1,
                "profile_attrs": [a for a in prof if a is not None], "known_skills": (), "years_exp": p.get("years_exp"),
                "degree_ord": p.get("degree_ord")}

    def _make_env(self, seeker: dict, sim=None):
        from jobunicorn.env.conv_env import ConvEnv
        from jobunicorn.retrieval.two_stage import TwoStageRetriever

        retr = TwoStageRetriever(self.W, 2000)
        retr._index = self.faiss_cache  # share the FAISS index across conversations
        env = ConvEnv(self.W, self.envcfg, fit=SafeFit(self.fit_base, self.nU0, self.nJ0), retriever=retr)
        live = sim if sim is not None else LiveUser()
        sess = self._session(seeker)
        sess["history"] = sess["history"] + sorted(self.closed)  # exclude applied + closed jobs from the pool
        env.reset(sess, live)
        return env, live

    def describe(self, act: tuple) -> dict:
        kind, payload = act
        W = self.W
        if kind == "rec":
            return {"type": "rec", "jobs": [int(j) for j in payload], "text": "Dựa trên những gì bạn chia sẻ, đây là 10 việc làm phù hợp nhất. Bạn thấy việc nào ưng ý không?"}
        if kind == "binary":
            a = self.attr_info(payload)
            return {"type": "binary", "attr": a, "text": f"Bạn có muốn công việc có {a['type_vi']} “{a['label']}” không?"}
        if kind == "choice":
            t, opts = payload
            return {"type": "choice", "attr_type": t, "options": [self.attr_info(a) for a in opts],
                    "text": f"Bạn quan tâm {TYPE_VI.get(t, t)} nào sau đây? (có thể chọn nhiều)"}
        if kind == "hier":
            return {"type": "hier", "options": [self.attr_info(a) for a in payload], "text": "Bạn muốn làm trong ngành nghề nào? (có thể chọn nhiều)"}
        if kind == "range":
            opts = [self.attr_info(W.offset["seniority"] + k) for k in range(5)]
            return {"type": "range", "options": opts, "text": "Bạn muốn ứng tuyển ở cấp bậc nào?"}
        if kind == "confirm":
            a = self.attr_info(payload)
            return {"type": "confirm", "attr": a, "text": f"Bạn muốn tìm việc tại {a['label']} ({a['name']}) đúng không?"}
        return {"type": kind, "text": str(kind)}

    def _next(self, c: Conv) -> dict:
        from jobunicorn.policy.unicorn import observe, policy_action

        env = c.env
        if env.done:
            c.pending = None
            return {"done": True, "success": env.success_turn is not None, "turn": env.t}
        st, a, act = policy_action(env, self.agent, self.pc, True, pre=c.pre)
        c.pending = act
        d = self.describe(act)
        d.update(done=False, turn=env.t + 1, max_turns=env.cfg.T, n_candidates=int(len(env.cand)),
                 top10_mass=float(np.sort(env.b)[::-1][:10].sum()) if len(env.b) else 0.0)
        return d

    def start(self, seeker: dict) -> tuple[Conv, dict]:
        with self.lock:
            env, live = self._make_env(seeker)
            c = Conv(id=uuid.uuid4().hex, seeker_id=seeker["id"], env=env, live=live)
            self.convs[c.id] = c
            self._gc()
            return c, self._next(c)

    def answer(self, conv_id: str, ans) -> tuple[Conv, dict]:
        """ans: 'yes'|'no'|'whatever' | list of attr ids | [lo, hi] | state attr id | rank (int, 1-based) | None."""
        from jobunicorn.policy.unicorn import observe

        with self.lock:
            c = self.convs[conv_id]
            if c.pending is None:
                return c, {"done": True, "success": c.env.success_turn is not None, "turn": c.env.t}
            kind = c.pending[0]
            if kind == "range" and isinstance(ans, (list, tuple)):
                ans = (int(ans[0]), int(ans[1]))
            elif kind in ("choice", "hier") and isinstance(ans, list):
                ans = [int(x) for x in ans]
            elif kind == "confirm" and ans not in (YES,) and ans is not None:
                ans = int(ans)
            elif kind == "rec":
                ans = int(ans) if ans else None
            c.live.answer = ans
            q = self.describe(c.pending)
            r, done, _ = c.env.step(c.pending)
            c.turns.append({"turn": c.env.t, "question": q, "answer": ans if not isinstance(ans, tuple) else list(ans)})
            c.pre = observe(c.env, self.pc) if not done else None
            return c, self._next(c)

    def answer_text(self, kind: str, ans) -> str:
        if kind == "rec":
            return f"Chọn việc thứ {ans}" if ans else "Chưa ưng ý"
        if ans == WHATEVER:
            return "Sao cũng được"
        if kind == "binary":
            return {YES: "Có", NO: "Không"}.get(ans, str(ans))
        if kind in ("choice", "hier"):
            return ", ".join(self.attr_info(a)["label"] for a in ans) if ans else "Không cái nào"
        if kind == "range":
            names = ["entry", "mid", "senior", "manager", "executive"]
            return f"{SEN_VI[names[ans[0]]]} → {SEN_VI[names[ans[1]]]}"
        if kind == "confirm":
            return "Đúng" if ans == YES else f"Không, muốn ở {self.attr_info(int(ans))['label']}"
        return str(ans)

    def simulate(self, target: int, personas: list[dict], p_unknown_skill: float = 0.5) -> list[dict]:
        """Model test for a job: for each persona, the rule-based simulator of the report plays a seeker whose ONLY
        target is this job, and the R3 policy runs the conversation. Profile-only personas use a scratch embedding row."""
        from jobunicorn.policy.unicorn import observe, policy_action
        from jobunicorn.simulator.rule import SimConfig, UserSimulator

        out = []
        with self.lock:
            free = iter(self.scratch)
            personas = [dict(p) for p in personas]
            used = []
            for p in personas:
                if p.get("world_idx") is None:
                    p["world_idx"] = next(free)
                    self.web_users[p["world_idx"]] = dict(p, applied=[])
                    used.append(p["world_idx"])
            if used:
                self._reembed()
            for k, p in enumerate(personas):
                p["history"] = [h for h in p.get("history", []) if h != target]
                sim = UserSimulator(self.W, [int(target)], SimConfig(tau=0.5, eps=0.0, p_unknown_skill=p_unknown_skill, seed=k),
                                    rng=np.random.default_rng(1000 + k))
                env, _ = self._make_env(p, sim=sim)
                reachable = bool(np.isin(target, env.pool))
                init_rank = None
                if np.isin(target, env.cand):
                    order = env.cand[np.argsort(-env.b)]
                    init_rank = int(np.flatnonzero(order == target)[0]) + 1
                turns, pre = [], None
                while not env.done:
                    _st, _a, act = policy_action(env, self.agent, self.pc, True, pre=pre)
                    q = self.describe(act)
                    _r, done, info = env.step(act)
                    t = {"turn": env.t, "type": q["type"], "question": q["text"] if q["type"] != "rec" else "Gợi ý 10 việc",
                         "answer": self.answer_text(act[0], info.get("rank") if act[0] == "rec" else info.get("answer"))}
                    if act[0] == "rec":
                        t["jobs"] = [int(j) for j in info.get("list", [])]
                        t["target_in_list"] = info.get("rank")
                    turns.append(t)
                    pre = observe(env, self.pc) if not done else None
                out.append({"label": p.get("label"), "seeker_id": p.get("id"), "reachable": reachable, "initial_rank": init_rank,
                            "found": env.success_turn is not None, "turn": env.success_turn, "rank": env.success_rank,
                            "n_questions": sum(1 for t in turns if t["type"] != "rec"), "turns": turns})
            for i in used:
                self.web_users.pop(i, None)
        return out

    def quick_recommend(self, seeker: dict, k: int = 10) -> list[int]:
        """No conversation: top-k by belief right after reset (= Abs Greedy rule)."""
        with self.lock:
            env, _ = self._make_env(seeker)
            order = np.argsort(-env.b)[:k]
            return [int(j) for j in env.cand[order]]

    def similar_users(self, job_world_idx: int, user_rows: np.ndarray, k: int = 20) -> list[tuple[int, float]]:
        """Recruiter side: seekers whose embedding best matches the job (e_u . e_v)."""
        s = self.W.E_user[user_rows] @ self.W.E_job[job_world_idx]
        top = np.argsort(-s)[:k]
        return [(int(user_rows[i]), float(s[i])) for i in top]

    def fit_score(self, user_idx: int | None, job_idx: int | None) -> dict | None:
        if user_idx is None or job_idx is None or user_idx >= self.nU0 or job_idx >= self.nJ0:
            return None
        z = float(self.fit_base.logit(int(user_idx), np.asarray([int(job_idx)]))[0])
        unq = bool(self.fit_base.data.unqualified(int(user_idx), np.asarray([int(job_idx)]))[0])
        return {"logit": z, "prob": float(1 / (1 + np.exp(-z))), "unqualified": unq}

    def _gc(self, ttl: float = 3600):
        now = time.time()
        for k in [k for k, c in self.convs.items() if now - c.created > ttl]:
            self.convs.pop(k, None)


_ENGINE: Engine | None = None
_ERR: str | None = None


def get_engine() -> Engine | None:
    return _ENGINE


def engine_error() -> str | None:
    return _ERR


def load_engine() -> None:
    global _ENGINE, _ERR
    try:
        _ENGINE = Engine()
    except Exception as e:  # keep the web app usable without the recommender
        import traceback

        traceback.print_exc()
        _ERR = f"{type(e).__name__}: {e}"
