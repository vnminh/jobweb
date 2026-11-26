"""Run a conversational policy (rules or DQN) on simulated sessions — used by P6, P7, P9, P10.

Rules (local CPU, parallel):
  python scripts/conv_run.py --config configs/p6_conv.yaml run.policy=max_entropy run.sim_mode=multi run.split=val
DQN (Modal GPU):
  modal run modal_app.py --gpu --cmd "python scripts/conv_run.py --config configs/p6_conv.yaml --data-root /vol/data \
      --out /vol/reports/p6_baseline/unicorn_multi run.policy=dqn run.sim_mode=multi"
Outputs in --out: summary.json, episodes.parquet, train_curve.json (DQN), policy.pt (DQN), run_manifest.json
"""

from __future__ import annotations

import dataclasses
import json
import multiprocessing as mp
import sys
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd

from jobunicorn.config import REPO_ROOT, base_arg_parser, resolve_config
from jobunicorn.env.conv_env import ConvEnv, EnvConfig
from jobunicorn.env.world import World, load_world
from jobunicorn.eval.conv_metrics import episode_record, summarize
from jobunicorn.logging_utils import get_logger, write_manifest
from jobunicorn.policy.rules import AbsGreedy, EIGThreshold, MaxEntropy, Oracle, RandomPolicy
from jobunicorn.simulator.rule import SimConfig, UserSimulator

log = get_logger("conv")
G: dict = {}  # globals shared with forked workers


# ---------------------------------------------------------------------- sessions

def attr_maps(world: World, dr: Path) -> dict:
    gd = dr / "processed" / "graph"
    m = {}
    for t in ("state", "city", "occupation", "seniority", "skill"):
        n = pd.read_parquet(gd / f"nodes_{t}.parquet")
        m[t] = dict(zip(n["key"], n["idx"] + world.offset[t]))
    return m


def load_sessions(dr: Path, split: str, world: World, maps: dict, known_skills: dict | None) -> list[dict]:
    s = pd.read_parquet(dr / "processed" / "sessions" / f"{split}.parquet")
    out = []
    for r in s.itertuples(index=False):
        st = maps["state"].get(r.state_key, -1) if isinstance(r.state_key, str) else -1
        prof = [maps["occupation"].get(r.last_occ), maps["seniority"].get(r.seniority), maps["city"].get(r.city_key), st if st >= 0 else None]
        out.append({"user_idx": int(r.user_idx), "user_id": int(r.user_id), "window": int(r.window), "role": r.role,
                    "targets": [int(x) for x in r.targets], "history": [int(x) for x in r.history], "state_attr": int(st),
                    "profile_attrs": [int(a) for a in prof if a is not None],
                    "known_skills": known_skills.get(int(r.user_id), ()) if known_skills else (),
                    "years_exp": None if pd.isna(r.years_exp) else float(r.years_exp),
                    "degree_ord": None if pd.isna(r.degree_ord) else int(r.degree_ord)})
    return out


def expand(sessions: list[dict], mode: str) -> list[dict]:
    if mode == "multi":
        return sessions
    return [dict(s, targets=[t], parent=i) for i, s in enumerate(sessions) for t in s["targets"]]


def calibrate_temp(world: World, sessions: list[dict], n: int = 300, seed: int = 0) -> float:
    """Std of e_u.e_v over each session's window jobs (train sessions), used as score temperature."""
    rng = np.random.default_rng(seed)
    vals = []
    for s in rng.choice(sessions, size=min(n, len(sessions)), replace=False):
        jobs = world.window_jobs[s["window"]]
        jobs = rng.choice(jobs, size=min(2000, len(jobs)), replace=False)
        vals.append(world.E_job[jobs] @ world.E_user[s["user_idx"]])
    return float(np.concatenate(vals).std())


# ---------------------------------------------------------------------- episodes

def make_policy(name: str, rcfg: dict, seed: int):
    if name == "oracle":
        return Oracle()
    if name == "random":
        return RandomPolicy(seed)
    if name == "abs_greedy":
        return AbsGreedy()
    if name == "max_entropy":
        return MaxEntropy(int(rcfg.get("rec_threshold", 50)))
    if name == "eig_threshold":
        return EIGThreshold(float(rcfg.get("mass_threshold", 0.1)), int(rcfg.get("ask_budget", 4)))
    raise ValueError(name)


def run_episode(env: ConvEnv, sess: dict, simcfg: SimConfig, policy=None, agent=None, pc=None, greedy=True, seed=0, learn=False):
    sim = UserSimulator(env.W, sess["targets"], dataclasses.replace(simcfg, seed=seed), known_skills=set(np.asarray(sess.get("known_skills", ())).tolist()),
                        rng=np.random.default_rng(seed))
    env.reset(sess, sim)
    reach = bool(np.isin(sess["targets"], env.pool).any())
    total = 0.0
    pre = None
    while not env.done:
        if agent is not None:
            from jobunicorn.policy.unicorn import observe, policy_action

            st, a, act = policy_action(env, agent, pc, greedy, pre=pre)
            r, done, _ = env.step(act)
            total += r
            pre = observe(env, pc) if not done else None
            if learn:
                agent.push(st, a, r, pre[0] if pre is not None else None, done)
                for _ in range(pc.updates_per_step):
                    agent.update()
        else:
            r, done, _ = env.step(policy.act(env))
            total += r
    rec = episode_record(env)
    rec.update(user_id=sess["user_id"], n_targets=len(sess["targets"]), reachable=reach, return_=total,
               n_hist=len(sess["history"]), window=sess["window"])
    return rec


def _worker(args):
    i, sess = args
    env = ConvEnv(G["world"], G["envcfg"], fit=G.get("fit"), retriever=G.get("retriever"))
    pol = make_policy(G["policy"], G["rcfg"], G["seed"] + i)
    return run_episode(env, sess, G["simcfg"], policy=pol, seed=G["seed"] * 100003 + i)


def evaluate_rules(sessions, n_proc: int) -> pd.DataFrame:
    with mp.get_context("fork").Pool(n_proc) as pool:
        recs = pool.map(_worker, list(enumerate(sessions)), chunksize=8)
    return pd.DataFrame(recs)


FIT_CACHE: dict = {}  # preloaded by conv_batch in the parent process (shared copy-on-write across workers)


def build_fit(cfg, dr, world):
    fcfg = cfg.get("fit_model")
    if not fcfg or not (cfg["env"].get("lambda_fit") or cfg["env"].get("beta_fit")):
        return None
    from jobunicorn.fit.scorer import FitScorer

    key = fcfg.get("model", "g_phi")
    if key in FIT_CACHE:
        base = FIT_CACHE[key]
        return FitScorer(base.data, base.model, base.scaler, base.base)  # fresh per-session cache, shared data
    return FitScorer.load(dr, world, fcfg)


def build_retriever(cfg, world):
    n_c = cfg.get("retrieval", {}).get("n_c")
    if not n_c:
        return None
    from jobunicorn.retrieval.two_stage import TwoStageRetriever

    return TwoStageRetriever(world, int(n_c))


# ---------------------------------------------------------------------- transcripts

def _q_text(world: World, action: tuple) -> str:
    kind, payload = action
    nm = lambda a: world.attr_name[a].split(":", 1)[1] + f" ({world.type_of(a)})"
    if kind == "binary":
        return f"Hỏi có/không: {nm(payload)}?"
    if kind == "choice":
        return f"Chọn (loại {payload[0]}): " + " | ".join(world.attr_name[a].split(":", 1)[1] for a in payload[1])
    if kind == "hier":
        return "Chọn nhóm nghề: " + " | ".join(world.attr_name[a].split(":", 1)[1] for a in payload)
    if kind == "range":
        return "Hỏi khoảng cấp bậc (entry..executive)"
    if kind == "confirm":
        return f"Xác nhận nơi tìm việc: {world.attr_name[payload].split(':', 1)[1]}?"
    if kind == "init":
        return f"[user nêu trước] {nm(payload)}"
    return kind


def write_dialogues(path: Path, env: ConvEnv, sessions: list[dict], simcfg: SimConfig, job_names, policy=None, agent=None, pc=None) -> None:
    W = env.W
    lines = ["# 10 phiên minh hoạ\n"]
    for i, sess in enumerate(sessions):
        rec = run_episode(env, sess, simcfg, policy=policy, agent=agent, pc=pc, greedy=True, seed=424242 + i)
        tnames = "; ".join(str(job_names[j])[:60] for j in sess["targets"][:5])
        lines.append(f"\n## Phiên {i + 1} — user {sess['user_id']} (window {sess['window']}), {len(sess['targets'])} job đích: {tnames}\n")
        for h in env.history:
            act = h["action"]
            if act[0] == "rec":
                L = h.get("list", [])
                hit = h.get("rank")
                lines.append(f"- Lượt {h['turn']}: **Gợi ý** {len(L)} job: " + "; ".join(str(job_names[j])[:40] for j in L[:5])
                             + (" …" if len(L) > 5 else "") + f" → {'CHẤP NHẬN hạng ' + str(hit) if hit else 'từ chối'}")
            else:
                ans = h.get("answer")
                if isinstance(ans, list):
                    ans = ", ".join(W.attr_name[a].split(":", 1)[1] for a in ans) or "không cái nào"
                elif isinstance(ans, (int, np.integer)) and act[0] == "confirm":
                    ans = "không, muốn ở " + W.attr_name[int(ans)].split(":", 1)[1]
                lines.append(f"- Lượt {h['turn']}: {_q_text(W, act)} → {ans}")
        lines.append(f"\nKết quả: {'thành công ở lượt ' + str(rec['success_turn']) if rec['success'] else 'thất bại'}; công sức = {rec['effort']}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------- main

def main(argv=None) -> int:
    args = base_arg_parser(__doc__).parse_args(argv)
    cfg = resolve_config(args)
    dr = Path(cfg["paths"]["data_root"])
    world = load_world(dr)
    return execute(cfg, world, attr_maps(world, dr))


def execute(cfg: dict, world: World, maps: dict) -> int:
    """Run one configuration (rules evaluation or DQN training + evaluation) with an already-loaded world."""
    rc = cfg["run"]
    dr = Path(cfg["paths"]["data_root"])
    out = Path(cfg["paths"].get("out") or REPO_ROOT / "reports" / rc.get("phase", "conv") / rc.get("name", "run"))
    out.mkdir(parents=True, exist_ok=True)
    T0 = time.time()
    seed = int(cfg["seed"])
    known = None
    if cfg["sim"].get("p_unknown_skill", 0) > 0:
        # only users that appear in sessions, stored as compact int32 arrays (sets built per episode)
        sess_users = set()
        for sp_name in ("train", "val", "test"):
            sess_users |= set(pd.read_parquet(dr / "processed" / "sessions" / f"{sp_name}.parquet", columns=["user_id"])["user_id"])
        us = pd.read_parquet(dr / "processed" / "attributes" / "user_skills.parquet", columns=["user_id", "skill_id"])
        us = us[us.user_id.isin(sess_users)]
        us = us.assign(a=us.skill_id.map(maps["skill"])).dropna()
        us["a"] = us["a"].astype(np.int32)
        known = {int(u): g.to_numpy() for u, g in us.groupby("user_id")["a"]}
    train_s = load_sessions(dr, "train", world, maps, known)
    prefix = cfg.get("world", {}).get("emb_prefix", "node_emb")
    if prefix != "node_emb":
        world = load_world(dr, emb_prefix=prefix)  # ablation: different node embeddings (e.g. text-only encoder)
        maps = attr_maps(world, dr)
    temp_path = dr / "processed" / "sessions" / ("score_temp.json" if prefix == "node_emb" else f"score_temp_{prefix}.json")
    if temp_path.exists():
        temp = json.loads(temp_path.read_text())["score_temp"]
    else:
        temp = calibrate_temp(world, train_s, seed=0)
        temp_path.write_text(json.dumps({"score_temp": temp, "source": "calibrate_temp on 300 train sessions"}))
    envcfg = EnvConfig(**{**cfg["env"], "score_temp": temp, "seed": seed})
    simcfg = SimConfig(**cfg["sim"], seed=seed)
    split = rc["split"]
    if split == "test" and not rc.get("allow_test", False):
        raise SystemExit("window 7 (test) is reserved for P10/P11: set run.allow_test=true only there")
    eval_s = expand(load_sessions(dr, split, world, maps, known), rc["sim_mode"])
    rng = np.random.default_rng(12345)  # fixed evaluation sample across all methods
    if rc.get("n_eval") and len(eval_s) > int(rc["n_eval"]):
        eval_s = [eval_s[i] for i in sorted(rng.choice(len(eval_s), int(rc["n_eval"]), replace=False))]
    fit = build_fit(cfg, dr, world)
    retriever = build_retriever(cfg, world)
    log.info(f"world {world.n_attr} attrs, temp {temp:.3f}, eval {len(eval_s)} sessions ({split}, {rc['sim_mode']}), {time.time() - T0:.0f}s")
    G.update(world=world, envcfg=envcfg, simcfg=simcfg, policy=rc["policy"], rcfg=rc, seed=seed, fit=fit, retriever=retriever)
    extra = {}
    if rc["policy"] != "dqn":
        if int(rc.get("n_proc", 12)) > 1:
            df = evaluate_rules(eval_s, int(rc.get("n_proc", 12)))
        else:
            df = pd.DataFrame([_worker((i, s)) for i, s in enumerate(eval_s)])
    else:
        import torch

        from jobunicorn.policy.unicorn import DQNAgent, PolicyConfig

        pc = PolicyConfig(**cfg.get("policy", {}))
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        tr = expand([s for s in train_s if s["role"] == "train"], rc["sim_mode"])
        es = expand([s for s in train_s if s["role"] == "es"], rc["sim_mode"])
        es = [es[i] for i in np.random.default_rng(7).choice(len(es), min(len(es), int(rc.get("n_es", 300))), replace=False)]
        n_ep = 0 if rc.get("load_policy") else int(rc["train_episodes"])
        agent = DQNAgent(pc, device, total_steps=max(1, n_ep) * 8, seed=seed, tables=(world.E_user, world.E_attr, world.E_job))
        env = ConvEnv(world, envcfg, fit=fit, retriever=retriever)
        curve, best, best_state = [], -1e9, None
        erng = np.random.default_rng(seed)
        t1 = time.time()
        rets = []
        start_ep, sec0 = 1, 0.0
        ckpt = out / "ckpt.pt"
        if n_ep and ckpt.exists():
            # resume after a lost container (preemption / account switch). The replay buffer is NOT saved (~1 GB):
            # it refills from the resumed policy, so learning pauses for ~warmup transitions.
            import random as _random

            ck = torch.load(ckpt, map_location="cpu", weights_only=False)
            agent.q.load_state_dict(ck["q"])
            agent.qt.load_state_dict(ck["qt"])
            agent.opt.load_state_dict(ck["opt"])
            agent.steps, agent.losses = ck["steps"], ck["losses"]
            curve, best, best_state, rets = ck["curve"], ck["best"], ck["best_state"], ck["rets"]
            erng.bit_generator.state = ck["erng"]
            np.random.set_state(ck["np_random"])
            _random.setstate(ck["py_random"])
            torch.set_rng_state(ck["torch_rng"].to(torch.uint8))
            start_ep, sec0 = ck["ep"] + 1, curve[-1]["sec"] if curve else 0.0
            t1 = time.time() - sec0
            log.info(f"resumed from {ckpt} at episode {ck['ep']} (replay buffer restarts empty)")
        for ep in range(start_ep, n_ep + 1):
            s = tr[int(erng.integers(len(tr)))]
            rec = run_episode(env, s, simcfg, agent=agent, pc=pc, greedy=False, seed=seed * 7919 + ep, learn=True)
            rets.append(rec["return_"])
            if ep % int(rc.get("eval_every", 500)) == 0 or ep == n_ep:
                ev = pd.DataFrame([run_episode(env, x, simcfg, agent=agent, pc=pc, greedy=True, seed=10_000 + i) for i, x in enumerate(es)])
                sc = float(ev["hdcg"].mean())
                curve.append({"episode": ep, "train_return_avg": float(np.mean(rets[-int(rc.get('eval_every', 500)):])),
                              "es_SR@15": float(ev["success"].mean()), "es_hDCG": sc, "es_AT": float(ev["turn"].mean()),
                              "loss_avg": float(np.mean(agent.losses[-500:])) if agent.losses else None, "eps": agent.eps(),
                              "sec": time.time() - t1})
                log.info(curve[-1])
                if sc > best:
                    best = sc
                    best_state = {k: v.detach().cpu().clone() for k, v in agent.q.state_dict().items()}
                import random as _random

                torch.save({"ep": ep, "q": agent.q.state_dict(), "qt": agent.qt.state_dict(), "opt": agent.opt.state_dict(),
                            "steps": agent.steps, "losses": agent.losses[-1000:], "curve": curve, "best": best,
                            "best_state": best_state, "rets": rets, "erng": erng.bit_generator.state,
                            "np_random": np.random.get_state(), "py_random": _random.getstate(),
                            "torch_rng": torch.get_rng_state()}, str(ckpt) + ".tmp")
                os.replace(str(ckpt) + ".tmp", ckpt)
        if rc.get("load_policy"):
            best_state = torch.load(REPO_ROOT / rc["load_policy"], map_location=device)
        agent.q.load_state_dict(best_state)
        torch.save(best_state, out / "policy.pt")
        (out / "train_curve.json").write_text(json.dumps(curve, indent=2))
        df = pd.DataFrame([run_episode(env, x, simcfg, agent=agent, pc=pc, greedy=True, seed=seed * 100003 + i) for i, x in enumerate(eval_s)])
        extra["train_curve"] = curve
        G["agent"], G["pc"] = agent, pc
    n_cat = int(sum(len(world.window_jobs[w]) for w in {s["window"] for s in eval_s}))
    summ = summarize(df, T=envcfg.T, seed=seed, n_jobs_catalog=n_cat)
    summ["reachable_rate"] = float(df["reachable"].mean())
    summ["SR@15_given_reachable"] = float(df.loc[df.reachable, "success"].mean()) if df.reachable.any() else float("nan")
    qt = df["qtypes"].str.split("|").explode()
    summ["action_mix"] = qt[qt != ""].value_counts(normalize=True).round(4).to_dict()
    summ.update(policy=rc["policy"], sim_mode=rc["sim_mode"], split=split, score_temp=temp, env=dataclasses.asdict(envcfg),
                sim=dataclasses.asdict(simcfg), runtime_sec=time.time() - T0)
    if int(rc.get("n_dialogues", 10)) > 0:
        names = pd.read_parquet(dr / "processed" / "graph" / "nodes_job.parquet", columns=["name"])["name"].to_numpy()
        env_d = ConvEnv(world, envcfg, fit=fit, retriever=retriever)
        dsess = eval_s[: int(rc.get("n_dialogues", 10))]
        if rc["policy"] == "dqn":
            write_dialogues(out / "dialogues.md", env_d, dsess, simcfg, names, agent=G["agent"], pc=G["pc"])
        else:
            write_dialogues(out / "dialogues.md", env_d, dsess, simcfg, names, policy=make_policy(rc["policy"], rc, seed))
    df.drop(columns=["rec_jobs"]).to_parquet(out / "episodes.parquet", index=False)
    (out / "summary.json").write_text(json.dumps(summ, indent=2, default=str))
    write_manifest(out, cfg, extra={"runtime_sec": time.time() - T0})
    log.info(f"{rc['policy']} {rc['sim_mode']}: SR@15 {summ['SR@15']:.4f} AT {summ['AT']:.2f} hDCG {summ['hDCG']:.4f} ({time.time() - T0:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
