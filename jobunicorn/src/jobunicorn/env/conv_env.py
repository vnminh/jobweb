"""Conversational recommendation MDP (DESIGN 7; UNICORN 1.2 as the binary special case).

One class covers:
  * UNICORN baseline: binary questions, intersection filtering of accepted attributes, weighted entropy, UNICORN rewards;
  * JobUNICORN extensions (P7): choice / hierarchical / range / confirm questions, hard-vs-soft constraints with
    union-within-type, 'whatever' answers, EIG question scoring, extended rewards;
  * fit term (P8) via a pluggable scorer; two-stage retrieval (P9) via a pluggable retriever.

Actions are tuples:
  ("rec", [job idx ...])          recommend a list (length K)
  ("binary", a)                   ask attribute a (global attr id)
  ("choice", (type, [a ...]))     multiple choice over values of one type
  ("hier", [g ...])               multiple choice over parent nodes (occupation groups)
  ("range", type)                 ordinal range (seniority)
  ("confirm", state_attr)         confirm the profile location
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from jobunicorn.env.world import ORDINAL_TYPES, SINGLE_VALUED, World
from jobunicorn.simulator.rule import NO, WHATEVER, YES, UserSimulator

UNICORN_REWARDS = {"rec_suc": 1.0, "rec_fail": -0.1, "ask_suc": 0.01, "ask_fail": -0.1, "ask_whatever": -0.1, "quit": -0.3}
EXTENDED_REWARDS = {"rec_suc": 1.0, "rec_fail": -0.1, "ask_suc": 0.01, "ask_fail": -0.1, "ask_whatever": -0.05, "quit": -0.3}


@dataclass
class EnvConfig:
    T: int = 15
    K: int = 10
    Kv: int = 10
    Kq: int = 10
    question_types: tuple = ("binary",)
    binary_types: tuple = ("occ_group", "occupation", "skill", "seniority", "job_type", "city")
    choice_types: tuple = ("occupation", "skill", "seniority", "job_type", "city")
    choice_m: int = 4
    filter_mode: str = "intersection"  # 'intersection' (UNICORN) | 'soft' (JobUNICORN)
    hard_types: tuple = ("job_type", "city", "state")
    hard_keep_unknown: bool = True
    q_score: str = "wentropy"  # 'wentropy' | 'eig'
    location_mode: str = "hard_state"  # 'hard_state' | 'confirm'
    loc_bonus: float = 1.7  # logit bonus for same-state jobs before confirmation (~84% of apps are same-state)
    init_attr: bool = True
    init_types: tuple = ("occupation", "skill")
    reward_mode: str = "unicorn"  # 'unicorn' | 'extended'
    rewards: dict = field(default_factory=dict)
    lambda_fit: float = 0.0
    beta_fit: float = 0.0
    range_penalty: float = 0.5
    reject_list_penalty: float = 0.1
    score_temp: float = 1.0
    use_whatever_set: bool = False  # DESIGN 7.5 'D' (extended)
    # Belief over candidates (post-P10 diagnostics; defaults reproduce P10):
    #   'sigmoid': w = sigma(s / score_temp), b = w / sum(w)  (saturates on the top-N_c tail -> nearly uniform b)
    #   'softmax': b = softmax(s / belief_temp), w = b / max(b)  (belief_temp fitted by likelihood on train sessions)
    belief: str = "sigmoid"
    belief_temp: float = 0.0  # 0 -> score_temp
    exclude_history: bool = False  # drop jobs the user already applied to (history) from the pool
    turn_penalty: float = 0.0  # subtracted from every turn's reward (aligns the return with hDCG's turn discount)
    seed: int = 0

    def reward_table(self) -> dict:
        base = dict(UNICORN_REWARDS if self.reward_mode == "unicorn" else EXTENDED_REWARDS)
        base.update(self.rewards or {})
        return base


def _hb(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-12, 1 - 1e-12)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def _ent(p: np.ndarray) -> float:
    p = p[p > 1e-12]
    return float(-(p * np.log(p)).sum())


class ConvEnv:
    def __init__(self, world: World, cfg: EnvConfig, fit=None, retriever=None):
        self.W = world
        self.cfg = cfg
        self.R = cfg.reward_table()
        self.fit = fit
        self.retriever = retriever
        self.rng = np.random.default_rng(cfg.seed)
        self.t_idx = {t: i for i, t in enumerate(world.types)}

    # ------------------------------------------------------------------ episode
    def reset(self, session: dict, sim: UserSimulator) -> None:
        W, c = self.W, self.cfg
        self.sess, self.sim = session, sim
        self.u = int(session["user_idx"])
        self.e_u = W.E_user[self.u]
        self.user_state = session.get("state_attr", -1)
        pool = W.window_jobs[int(session["window"])]
        if c.location_mode == "hard_state" and self.user_state is not None and self.user_state >= 0:
            pool = pool[W.job_state[pool] == self.user_state]
        if c.exclude_history and session.get("history"):
            pool = pool[~np.isin(pool, np.asarray(session["history"], dtype=np.int64))]
        self.pool = pool
        self.P_acc: list[int] = []
        self.alpha: dict[int, float] = {}
        self.P_rej: set[int] = set()
        self.V_rej: set[int] = set()
        self.asked: set[int] = set()
        self.asked_keys: set = set()
        self.D: set[str] = set()
        self.C_hard: dict[str, set[int]] = {}
        if c.location_mode == "hard_state" and self.user_state is not None and self.user_state >= 0:
            self.C_hard["state"] = {self.user_state}
        self.excluded_attrs: set[int] = set()  # rejected hard values
        self.focus: set[int] = set()
        self.rng_range: tuple[int, int] | None = None
        self.list_pen: set[int] = set()
        self.confirmed = c.location_mode != "confirm"
        self.t = 0
        self.done = False
        self.success_turn: int | None = None
        self.success_rank: int | None = None
        self.effort = 0
        self.history: list[dict] = []
        if c.init_attr:
            a = self._initial_attr()
            if a is not None:
                self._accept(a)
                self.asked.add(a)
                self.history.append({"turn": 0, "action": ("init", a), "answer": YES})
        self._refresh(filters=True)

    def _initial_attr(self) -> int | None:
        allowed = {self.t_idx[t] for t in self.cfg.init_types if t in self.t_idx}
        items = [(a, n) for a, n in self.sim.n.items() if self.W.attr_type[a] in allowed]
        if not items:
            return None
        good = [a for a, n in items if n >= self.sim.cfg.tau]
        if not good:
            m = max(n for _, n in items)
            good = [a for a, n in items if n == m]
        return int(self.rng.choice(good))

    # ------------------------------------------------------------------ state updates
    def _is_hard(self, a: int) -> bool:
        return self.cfg.filter_mode == "soft" and self.W.type_of(a) in self.cfg.hard_types

    def _accept(self, a: int, alpha: float = 1.0) -> None:
        t = self.W.type_of(a)
        if self._is_hard(a):
            self.C_hard.setdefault(t, set()).add(a)
        else:
            if a not in self.alpha:
                self.P_acc.append(a)
            self.alpha[a] = alpha

    def _reject(self, a: int) -> None:
        if self._is_hard(a):
            self.excluded_attrs.add(a)
        else:
            self.P_rej.add(a)

    def _jobs_with(self, a: int) -> np.ndarray:
        return self.W.AT.indices[self.W.AT.indptr[a]:self.W.AT.indptr[a + 1]]

    def _refresh(self, filters: bool) -> None:
        """Recompute candidate set (if filters changed), scores w and attribute masses pi."""
        W, c = self.W, self.cfg
        if filters:
            keep = np.ones(len(self.pool), dtype=bool)
            if c.filter_mode == "intersection":
                for a in self.P_acc:
                    keep &= np.isin(self.pool, self._jobs_with(a), assume_unique=False)
            for t, vals in self.C_hard.items():
                if t == "state" and c.location_mode == "hard_state":
                    continue  # pool already restricted
                has = np.zeros(len(self.pool), dtype=bool)
                for a in vals:
                    has |= np.isin(self.pool, self._jobs_with(a))
                if c.hard_keep_unknown and t in SINGLE_VALUED and t != "state":
                    tcol = W.A[self.pool][:, W.offset[t]:W.offset[t] + self._n_type(t)]
                    has |= np.asarray(tcol.sum(1)).ravel() == 0
                keep &= has
            for a in self.excluded_attrs:
                keep &= ~np.isin(self.pool, self._jobs_with(a))
            if self.V_rej:
                keep &= ~np.isin(self.pool, np.fromiter(self.V_rej, dtype=np.int64))
            cand = self.pool[keep]
            if self.retriever is not None:
                cand = self.retriever.select(self, cand)
            self.cand = cand
            self.A_cand = W.A[cand]
        s = W.E_job[self.cand] @ (self.e_u + sum(self.alpha[a] * W.E_attr[a] for a in self.P_acc) if self.P_acc else self.e_u)
        T = c.score_temp
        if self.P_rej:
            for a in self.P_rej:
                col = np.asarray(self.A_cand[:, a].todense()).ravel()
                if col.any():
                    s -= col * (W.E_job[self.cand] @ W.E_attr[a])
        if not self.confirmed and self.user_state is not None and self.user_state >= 0:
            s = s + c.loc_bonus * T * (W.job_state[self.cand] == self.user_state)
        if self.rng_range is not None:
            lv = W.job_seniority_ord[self.cand]
            lo, hi = self.rng_range
            dist = np.where(lv < 0, 0, np.maximum(lo - lv, 0) + np.maximum(lv - hi, 0))
            s = s - c.range_penalty * T * dist
        if self.list_pen:
            pen = np.asarray(self.A_cand[:, sorted(self.list_pen)].sum(1)).ravel()
            s = s - c.reject_list_penalty * T * pen
        if self.fit is not None and c.lambda_fit:
            s = s + c.lambda_fit * T * self.fit.score(self.sess, self.cand)
        s = np.asarray(s, dtype=np.float64)
        self.s = s
        if c.belief == "softmax" and len(s):
            z = s / (c.belief_temp or T)
            e = np.exp(z - z.max())
            self.b = e / e.sum()
            self.w = e  # = b / max(b): same ranking, top job has w = 1
        else:
            self.w = 1.0 / (1.0 + np.exp(-np.clip(s / T, -30, 30)))
            tot = self.w.sum()
            self.b = self.w / tot if tot > 0 else np.full(len(self.w), 1.0 / max(1, len(self.w)))
        self.pi = np.asarray(self.A_cand.T @ self.b).ravel() if len(self.cand) else np.zeros(W.n_attr)

    def _n_type(self, t: str) -> int:
        idx = self.t_idx[t]
        nxt = [self.W.offset[x] for x in self.W.types if self.W.offset[x] > self.W.offset[t]]
        return (min(nxt) if nxt else self.W.n_attr) - self.W.offset[t]

    # ------------------------------------------------------------------ candidates for the policy
    def top_items(self, k: int | None = None) -> np.ndarray:
        k = k or self.cfg.Kv
        if len(self.cand) == 0:
            return np.zeros(0, dtype=np.int64)
        k = min(k, len(self.cand))
        idx = np.argpartition(-self.w, k - 1)[:k]
        idx = idx[np.argsort(-self.w[idx])]
        return self.cand[idx]

    def _q_binary(self) -> list[tuple]:
        W, c = self.W, self.cfg
        allowed = np.zeros(len(W.types), dtype=bool)
        for t in c.binary_types:
            if t in self.t_idx and t not in self.D:
                allowed[self.t_idx[t]] = True
        mask = (self.pi > 0) & allowed[W.attr_type]
        if self.asked:
            mask[list(self.asked)] = False
        if self.focus and "occupation" in self.t_idx:
            occ = W.attr_type == self.t_idx["occupation"]
            mask &= ~occ | np.isin(W.attr_parent, list(self.focus))
        ids = np.flatnonzero(mask)
        if len(ids) == 0:
            return []
        p = self.pi[ids]
        sc = _hb(p) if c.q_score == "eig" else -(p * np.log(np.clip(p, 1e-12, 1)))
        top = ids[np.argsort(-sc)[: c.Kq]]
        return [(("binary", int(a)), float(sc[np.searchsorted(ids, a)]), 1) for a in top]

    def _choice_single(self, t: str, parents_only: bool = False) -> tuple | None:
        W, c = self.W, self.cfg
        off, n = W.offset[t], self._n_type(t)
        vals = np.arange(off, off + n)
        p = self.pi[off:off + n].copy()
        if self.asked:
            p[[a - off for a in self.asked if off <= a < off + n]] = 0
        if t == "occupation" and self.focus:
            p[~np.isin(W.attr_parent[vals], list(self.focus))] = 0
        if (p > 0).sum() < 2:
            return None
        top = np.argsort(-p)[: c.choice_m]
        top = top[p[top] > 0]
        px = p[top]
        other = max(0.0, 1.0 - px.sum())
        if c.q_score == "eig":
            sc = _ent(np.append(px, other))
        else:
            sc = float(-(px * np.log(px)).sum())
        return [int(v) for v in vals[top]], sc

    def _choice_multi(self, t: str) -> tuple | None:
        """Greedy choice of up to m values of a multi-valued type maximising the entropy of the answer pattern."""
        W, c = self.W, self.cfg
        off, n = W.offset[t], self._n_type(t)
        p = self.pi[off:off + n].copy()
        if self.asked:
            p[[a - off for a in self.asked if off <= a < off + n]] = 0
        cands = np.argsort(-np.minimum(p, 1 - p))[:30]
        cands = cands[p[cands] > 0]
        if len(cands) < 2:
            return None
        cols = np.asarray(self.A_cand[:, off + cands].todense()) > 0  # (n_cand, 30)
        chosen: list[int] = []
        code = np.zeros(len(self.cand), dtype=np.int64)
        best_sc = 0.0
        for step in range(c.choice_m):
            best = None
            for j in range(len(cands)):
                if j in chosen:
                    continue
                cd = code * 2 + cols[:, j]
                if c.q_score == "eig":
                    h = _ent(np.bincount(cd, weights=self.b))
                else:
                    pj = p[cands[j]]
                    h = best_sc + float(-pj * math.log(max(pj, 1e-12)))
                if best is None or h > best[1]:
                    best = (j, h)
            if best is None:
                break
            chosen.append(best[0])
            code = code * 2 + cols[:, best[0]]
            best_sc = best[1]
        return [int(off + cands[j]) for j in chosen], best_sc

    def candidate_questions(self) -> list[tuple]:
        """Top-Kq questions over all enabled types: list of (action, score, effort)."""
        c, W = self.cfg, self.W
        qs = []
        if "binary" in c.question_types:
            qs += self._q_binary()
        if "choice" in c.question_types:
            for t in c.choice_types:
                if t not in self.t_idx or t in self.D or ("choice", t) in self.asked_keys and t in SINGLE_VALUED and t != "occupation":
                    continue
                r = self._choice_single(t) if t in SINGLE_VALUED else self._choice_multi(t)
                if r:
                    qs.append((("choice", (t, r[0])), r[1], len(r[0])))
        if "hier" in c.question_types and not self.focus and "occ_group" in self.t_idx and "occ_group" not in self.D:
            r = self._choice_single("occ_group")
            if r:
                qs.append((("hier", r[0]), r[1], len(r[0])))
        if "range" in c.question_types and "seniority" in self.t_idx and ("range", "seniority") not in self.asked_keys and "seniority" not in self.D:
            lv = W.job_seniority_ord[self.cand]
            known = lv >= 0
            if known.any():
                dist = np.bincount(lv[known], weights=self.b[known], minlength=5)
                dist = dist / max(dist.sum(), 1e-12)
                sc = _ent(dist) if c.q_score == "eig" else float(-(dist[dist > 0] * np.log(dist[dist > 0])).sum())
                qs.append((("range", "seniority"), sc, 5))
        if "confirm" in c.question_types and not self.confirmed and self.user_state is not None and self.user_state >= 0:
            ps = float(self.b[W.job_state[self.cand] == self.user_state].sum())
            sc = float(_hb(np.array([ps]))[0]) if c.q_score == "eig" else -ps * math.log(max(ps, 1e-12))
            qs.append((("confirm", int(self.user_state)), sc, 1))
        qs.sort(key=lambda x: -x[1])
        return qs[: c.Kq]

    # ------------------------------------------------------------------ step
    def step(self, action: tuple) -> tuple[float, bool, dict]:
        assert not self.done
        c, R, W = self.cfg, self.R, self.W
        kind, payload = action
        self.t += 1
        info = {"turn": self.t, "kind": kind}
        r = 0.0
        filters = False
        if kind == "rec":
            L = [int(j) for j in payload][: c.K]
            self.effort += 0  # list reading counted separately
            rank = self.sim.recommend(L)
            unq = self.fit.unqualified_rate(self.sess, L) if (self.fit is not None and c.beta_fit) else 0.0
            info.update(rank=rank, list=L, unqualified=unq)
            if rank is not None:
                r = R["rec_suc"] if c.reward_mode == "unicorn" else R["rec_suc"] * (0.5 + 0.5 / math.log2(rank + 1))
                self.done, self.success_turn, self.success_rank = True, self.t, rank
            else:
                r = R["rec_fail"]
                self.V_rej.update(L)
                if c.filter_mode == "soft" and len(L):
                    cnt = np.asarray(W.A[L].sum(0)).ravel()
                    maj = np.flatnonzero(cnt > len(L) / 2)
                    self.list_pen.update(int(a) for a in maj if a not in self.asked and a not in self.alpha)
                filters = True
            r -= c.beta_fit * unq
        elif kind == "binary":
            a = int(payload)
            self.asked.add(a)
            self.effort += 1
            ans = self.sim.binary(a)
            info["answer"] = ans
            if ans == YES:
                self._accept(a)
                r = R["ask_suc"]
            elif ans == NO:
                self._reject(a)
                r = R["ask_fail"]
            else:
                r = R["ask_whatever"]
                if c.use_whatever_set:
                    self.D.add(W.type_of(a))
            filters = True
        elif kind in ("choice", "hier"):
            t, M = (payload if kind == "choice" else ("occ_group", payload))
            self.asked.update(M)
            self.asked_keys.add(("choice", t))
            self.effort += len(M)
            ans = self.sim.hier(M) if kind == "hier" else self.sim.choice(M)
            info["answer"] = ans
            if ans == WHATEVER:
                r = R["ask_whatever"]
                if c.use_whatever_set:
                    self.D.add(t)
            elif ans:
                for a in ans:
                    self._accept(a)
                    if kind == "hier":
                        self.focus.add(a)
                r = R["ask_suc"] * (min(3, len(ans)) if c.reward_mode == "extended" else 1)
                if t in SINGLE_VALUED and t not in c.hard_types:
                    for a in M:
                        if a not in ans:
                            self._reject(a)
            else:
                for a in M:
                    self._reject(a)
                r = R["ask_fail"]
            filters = True
        elif kind == "range":
            self.asked_keys.add(("range", payload))
            self.effort += 5
            lv = W.job_seniority_ord[np.asarray(self.sim.targets)]
            ans = self.sim.range(lv)
            info["answer"] = ans
            if ans == WHATEVER:
                r = R["ask_whatever"]
                if c.use_whatever_set:
                    self.D.add("seniority")
            else:
                self.rng_range = ans
                r = R["ask_suc"]
        elif kind == "confirm":
            s0 = int(payload)
            self.effort += 1
            ts = W.job_state[np.asarray(self.sim.targets)]
            ans = self.sim.confirm(s0, ts)
            info["answer"] = ans
            self.confirmed = True
            new = s0 if ans == YES else int(ans)
            self.C_hard["state"] = {new}
            r = R["ask_suc"]
            filters = True
        else:
            raise ValueError(kind)
        if not self.done and self.t >= c.T:
            self.done = True
            r += R["quit"]
        r -= c.turn_penalty
        self.history.append({"turn": self.t, "action": action, **{k: v for k, v in info.items() if k not in ("turn",)}})
        if not self.done:
            self._refresh(filters=filters)
        return r, self.done, info
