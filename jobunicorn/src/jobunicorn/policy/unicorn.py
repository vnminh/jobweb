"""Graph-based unified policy (UNICORN, Deng+21) and the JobUNICORN variant (DESIGN 7.7).

State graph per turn: user, accepted attributes, [profile nodes, rejected attributes], nodes of candidate questions,
top-Kv candidate jobs. Edges: user-job (w_v), job-attr (1), user-accepted attr (1), [user-profile (1), child-parent (1)].
Encoder: 2 graph layers (GCN for UNICORN; R-GCN with edge-type weights for JobUNICORN) -> 1 Transformer layer over
[user; accepted attrs (; profile; rejected with segment embeddings)] -> mean pool = f_S.
Q(s, a) = f_V(f_S) + f_A([f_S; e_a]) - mean_a f_A, e_a = mean of the action's member nodes (+ question-type embedding).
Training: Double DQN, soft target update, prioritized replay (proportional), epsilon-greedy.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

QTYPES = ["rec", "binary", "choice", "hier", "range", "confirm"]
NODE_TYPES = ["user", "acc", "cand_attr", "job", "profile", "rej"]
EDGE_TYPES = ["user_job", "job_attr", "user_acc", "user_profile", "child_parent"]


@dataclass
class PolicyConfig:
    hidden: int = 100
    emb_dim: int = 64
    graph_layer: str = "gcn"  # 'gcn' | 'rgcn'
    use_profile: bool = False
    use_rejected: bool = False
    use_qtype_emb: bool = False
    use_state_feats: bool = False  # post-P10: scalar dialogue features added to f_S (see state_features)
    rec_order: str = "q"  # 'q' (UNICORN: recommended list sorted by Q) | 'w' (sorted by env score)
    n_max: int = 96
    a_max: int = 24
    s_max: int = 40
    gamma: float = 0.999
    lr: float = 1e-4
    batch: int = 64
    buffer: int = 50000
    tau_soft: float = 0.01
    eps_start: float = 0.5
    eps_end: float = 0.05
    eps_decay_frac: float = 0.5
    per_alpha: float = 0.6
    per_beta0: float = 0.4
    warmup: int = 500
    updates_per_step: int = 1


# ---------------------------------------------------------------------- state encoding

N_STATE_FEATS = 8


def state_features(env) -> np.ndarray:
    """Scalars the graph cannot express: turn budget, candidate count, belief concentration, failures so far."""
    b = env.b if len(env.cand) else np.ones(1)
    k = min(env.cfg.K, len(b))
    top = np.sort(b)[::-1]
    ent = float(-(b[b > 0] * np.log(b[b > 0])).sum() / max(np.log(len(b)), 1e-6)) if len(b) > 1 else 0.0
    n_fail = sum(1 for h in env.history if h["action"][0] == "rec" and not h.get("rank"))
    n_ask = sum(1 for h in env.history if h["action"][0] not in ("rec", "init"))
    return np.array([env.t / env.cfg.T, np.log1p(len(env.cand)) / np.log1p(2000), float(top[:k].sum()), ent,
                     min(n_fail, 3) / 3, float(env.confirmed), min(n_ask, 6) / 6, float(top[0])], dtype=np.float32)


def encode_state(env, qs: list[tuple], items: np.ndarray, pc: PolicyConfig) -> dict:
    """Build the padded numpy description of the current state + candidate actions."""
    W = env.W
    src, nid, ntype, key2i = [], [], [], {}
    SRC = {"u": 0, "a": 1, "j": 2}

    def add(key, _vec, t):
        if key in key2i:
            return key2i[key]
        if len(src) >= pc.n_max:
            return None
        key2i[key] = len(src)
        src.append(SRC[key[0]])
        nid.append(env.u if key[0] == "u" else key[1])
        ntype.append(NODE_TYPES.index(t))
        return key2i[key]

    u = add(("u",), None, "user")
    seq, seg = [u], [0]
    edges = []  # (i, j, w, etype)
    for a in env.P_acc[-15:]:
        i = add(("a", a), W.E_attr[a], "acc")
        if i is not None:
            edges.append((u, i, 1.0, 2))
            seq.append(i)
            seg.append(1)
    if pc.use_profile:
        for a in env.sess.get("profile_attrs", []):
            i = add(("a", a), W.E_attr[a], "profile")
            if i is not None:
                edges.append((u, i, 1.0, 3))
                seq.append(i)
                seg.append(2)
    if pc.use_rejected:
        for a in list(env.P_rej)[-8:]:
            i = add(("a", a), W.E_attr[a], "rej")
            if i is not None:
                seq.append(i)
                seg.append(3)
    actions = []  # (member node idx list, qtype idx)
    refs = []  # aligned with actions: ('q', index in qs) | ('j', index in items)
    attr_nodes = []
    for qk, (act, _sc, _eff) in enumerate(qs):
        kind, payload = act
        if kind == "binary":
            mem = [payload]
        elif kind == "choice":
            mem = list(payload[1])
        elif kind == "hier":
            mem = list(payload)
        elif kind == "range":
            mem = [W.offset["seniority"] + k for k in range(5)]
        elif kind == "confirm":
            mem = [payload]
        else:
            mem = []
        idx = [add(("a", a), W.E_attr[a], "cand_attr") for a in mem]
        idx = [i for i in idx if i is not None]
        attr_nodes += [(a, i) for a, i in zip(mem, idx)]
        if idx:
            actions.append((idx, QTYPES.index(kind)))
            refs.append(("q", qk))
    w = dict(zip(env.cand.tolist(), env.w.tolist())) if len(items) else {}
    job_nodes = []
    for jk, j in enumerate(items.tolist()):
        i = add(("j", j), W.E_job[j], "job")
        if i is not None:
            edges.append((u, i, float(w.get(j, 0.5)), 0))
            job_nodes.append((j, i))
            actions.append(([i], 0))
            refs.append(("j", jk))
    # job-attr edges among nodes present
    if job_nodes:
        attrs_present = {k[1]: v for k, v in key2i.items() if k[0] == "a"}
        if attrs_present:
            ak = np.fromiter(attrs_present.keys(), dtype=np.int64)
            sub = W.A[[j for j, _ in job_nodes]][:, ak].tocoo()
            for r, cidx in zip(sub.row, sub.col):
                edges.append((job_nodes[r][1], attrs_present[int(ak[cidx])], 1.0, 1))
            for a, i in attrs_present.items():
                p = int(W.attr_parent[a])
                if p >= 0 and p in attrs_present:
                    edges.append((i, attrs_present[p], 1.0, 4))
    n = len(src)
    NS = np.zeros(pc.n_max, np.int8)
    NI = np.zeros(pc.n_max, np.int64)
    NS[:n] = src
    NI[:n] = nid
    T = np.zeros(pc.n_max, np.int8)
    T[:n] = ntype
    E = np.array(edges, dtype=np.float32).reshape(-1, 4)
    S = np.zeros(pc.s_max, np.int64)
    G = np.zeros(pc.s_max, np.int64)
    sl = min(len(seq), pc.s_max)
    S[:sl] = seq[:sl]
    G[:sl] = seg[:sl]
    na = min(len(actions), pc.a_max)
    AM = np.zeros((pc.a_max, 8), np.int64)
    AL = np.zeros(pc.a_max, np.int64)
    AQ = np.zeros(pc.a_max, np.int64)
    for k, (mem, q) in enumerate(actions[:na]):
        mem = mem[:8]
        AM[k, :len(mem)] = mem
        AL[k] = len(mem)
        AQ[k] = q
    Fs = state_features(env) if pc.use_state_feats else np.zeros(N_STATE_FEATS, np.float32)
    return {"F": Fs, "NS": NS, "NI": NI, "T": T, "n": n, "E": E, "S": S, "G": G, "sl": sl, "AM": AM, "AL": AL, "AQ": AQ, "na": na, "refs": refs[:na]}


def collate(states: list[dict], device, tables) -> dict:
    """tables = (E_user, E_attr, E_job) numpy arrays; node features are gathered here (replay stores indices only)."""
    B = len(states)
    n_max = states[0]["NS"].shape[0]
    NS = np.stack([s["NS"] for s in states])
    NI = np.stack([s["NI"] for s in states])
    X = np.zeros((B, n_max, tables[0].shape[1]), np.float32)
    for k in range(3):
        m = NS == k
        if k == 0:
            m &= np.arange(n_max)[None, :] == 0
        if m.any():
            X[m] = tables[k][NI[m]]
    X = torch.as_tensor(X, device=device)
    T = torch.as_tensor(np.stack([s["T"] for s in states]).astype(np.int64), device=device)
    ns = np.array([s["n"] for s in states])
    nmask = torch.as_tensor(np.arange(n_max)[None, :] < ns[:, None], device=device)
    A = torch.zeros(B, len(EDGE_TYPES), n_max, n_max, device=device)
    Es = [np.c_[np.full(len(s["E"]), b), s["E"]] for b, s in enumerate(states) if len(s["E"])]
    if Es:
        e = torch.as_tensor(np.concatenate(Es), device=device)
        b, i, j, w, t = e[:, 0].long(), e[:, 1].long(), e[:, 2].long(), e[:, 3].float(), e[:, 4].long()
        A[b, t, i, j] = w
        A[b, t, j, i] = w
    out = {k: torch.as_tensor(np.stack([s[k] for s in states]), device=device) for k in ("S", "G", "AM", "AL", "AQ")}
    out["F"] = torch.as_tensor(np.stack([s.get("F", np.zeros(N_STATE_FEATS, np.float32)) for s in states]), device=device)
    out.update(X=X, T=T, nmask=nmask, A=A,
               sl=torch.as_tensor([s["sl"] for s in states], device=device), na=torch.as_tensor([s["na"] for s in states], device=device))
    return out


# ---------------------------------------------------------------------- network

class QNet(nn.Module):
    def __init__(self, pc: PolicyConfig):
        super().__init__()
        h = pc.hidden
        self.pc = pc
        self.inp = nn.Linear(pc.emb_dim, h)
        self.temb = nn.Embedding(len(NODE_TYPES), h)
        if pc.graph_layer == "rgcn":
            self.W = nn.ModuleList([nn.ModuleList([nn.Linear(h, h, bias=False) for _ in EDGE_TYPES]) for _ in range(2)])
            self.W0 = nn.ModuleList([nn.Linear(h, h) for _ in range(2)])
        else:
            self.W = nn.ModuleList([nn.Linear(h, h) for _ in range(2)])
        self.seg = nn.Embedding(4, h)
        self.tr = nn.TransformerEncoderLayer(d_model=h, nhead=4, dim_feedforward=2 * h, dropout=0.0, batch_first=True)
        self.qemb = nn.Embedding(len(QTYPES), h)
        self.fV = nn.Sequential(nn.Linear(h, h), nn.ReLU(), nn.Linear(h, 1))
        self.fA = nn.Sequential(nn.Linear(2 * h, h), nn.ReLU(), nn.Linear(h, 1))
        if pc.use_state_feats:
            self.feat = nn.Sequential(nn.Linear(N_STATE_FEATS, h), nn.ReLU(), nn.Linear(h, h))

    def _norm(self, A: torch.Tensor, nmask: torch.Tensor) -> torch.Tensor:
        eye = torch.diag_embed(nmask.float())
        A = A + eye
        d = A.sum(-1).clamp(min=1e-6).pow(-0.5)
        return d.unsqueeze(-1) * A * d.unsqueeze(-2)

    def forward(self, s: dict) -> torch.Tensor:
        pc = self.pc
        H = F.relu(self.inp(s["X"]) + self.temb(s["T"])) * s["nmask"].unsqueeze(-1)
        if pc.graph_layer == "rgcn":
            An = [self._norm(s["A"][:, r], s["nmask"]) for r in range(len(EDGE_TYPES))]
            for l in range(2):
                m = self.W0[l](H)
                for r in range(len(EDGE_TYPES)):
                    m = m + An[r] @ self.W[l][r](H)
                H = F.relu(m) * s["nmask"].unsqueeze(-1)
        else:
            An = self._norm(s["A"].sum(1), s["nmask"])
            for l in range(2):
                H = F.relu(An @ self.W[l](H)) * s["nmask"].unsqueeze(-1)
        B = H.shape[0]
        seqh = H[torch.arange(B, device=H.device).unsqueeze(1), s["S"]]
        smask = torch.arange(s["S"].shape[1], device=H.device).unsqueeze(0) < s["sl"].unsqueeze(1)
        if pc.use_profile or pc.use_rejected:
            seqh = seqh + self.seg(s["G"])
        z = self.tr(seqh, src_key_padding_mask=~smask)
        fS = (z * smask.unsqueeze(-1)).sum(1) / smask.sum(1, keepdim=True).clamp(min=1)
        if pc.use_state_feats:
            fS = fS + self.feat(s["F"])
        mem = H[torch.arange(B, device=H.device).view(B, 1, 1), s["AM"]]  # B, a_max, 8, h
        mm = (torch.arange(s["AM"].shape[2], device=H.device).view(1, 1, -1) < s["AL"].unsqueeze(-1)).float()
        ea = (mem * mm.unsqueeze(-1)).sum(2) / mm.sum(2, keepdim=True).clamp(min=1)
        if pc.use_qtype_emb:
            ea = ea + self.qemb(s["AQ"])
        adv = self.fA(torch.cat([fS.unsqueeze(1).expand_as(ea), ea], -1)).squeeze(-1)
        amask = torch.arange(adv.shape[1], device=H.device).unsqueeze(0) < s["na"].unsqueeze(1)
        adv_mean = (adv * amask).sum(1, keepdim=True) / amask.sum(1, keepdim=True).clamp(min=1)
        q = self.fV(fS) + adv - adv_mean
        return q.masked_fill(~amask, -1e9)


# ---------------------------------------------------------------------- replay + agent

class PER:
    """Proportional prioritized replay (Schaul+16) with a flat array (buffer sizes here are small)."""

    def __init__(self, cap: int, alpha: float):
        self.cap, self.alpha = cap, alpha
        self.data: list = []
        self.prio = np.zeros(cap, np.float64)
        self.pos = 0

    def push(self, item) -> None:
        p = self.prio[: len(self.data)].max() if self.data else 1.0
        if len(self.data) < self.cap:
            self.data.append(item)
        else:
            self.data[self.pos] = item
        self.prio[self.pos] = p
        self.pos = (self.pos + 1) % self.cap

    def sample(self, n: int, beta: float):
        P = self.prio[: len(self.data)] ** self.alpha
        P = P / P.sum()
        idx = np.random.choice(len(self.data), n, p=P)
        w = (len(self.data) * P[idx]) ** (-beta)
        return idx, [self.data[i] for i in idx], w / w.max()

    def update(self, idx, td) -> None:
        self.prio[idx] = np.abs(td) + 1e-4

    def __len__(self):
        return len(self.data)


class DQNAgent:
    def __init__(self, pc: PolicyConfig, device, total_steps: int, seed: int = 0, tables=None):
        self.tables = tables
        torch.manual_seed(seed)
        random.seed(seed)
        np.random.seed(seed)
        self.pc, self.device = pc, device
        self.q = QNet(pc).to(device)
        self.qt = QNet(pc).to(device)
        self.qt.load_state_dict(self.q.state_dict())
        self.opt = torch.optim.Adam(self.q.parameters(), lr=pc.lr)
        self.buf = PER(pc.buffer, pc.per_alpha)
        self.total = max(1, total_steps)
        self.steps = 0
        self.losses: list[float] = []

    def eps(self) -> float:
        frac = min(1.0, self.steps / (self.pc.eps_decay_frac * self.total))
        return self.pc.eps_start + frac * (self.pc.eps_end - self.pc.eps_start)

    @torch.no_grad()
    def qvalues(self, st: dict) -> np.ndarray:
        self.q.eval()
        return self.q(collate([st], self.device, self.tables))[0, : st["na"]].cpu().numpy()

    def act(self, st: dict, greedy: bool) -> tuple[int, np.ndarray]:
        q = self.qvalues(st)
        if not greedy and random.random() < self.eps():
            return random.randrange(st["na"]), q
        return int(np.argmax(q)), q

    def push(self, s, a, r, s2, done) -> None:
        if s["na"] == 0 or a >= s["na"]:
            return  # no valid action (empty candidate set): nothing to learn from
        if s2 is not None and s2["na"] == 0:
            done = True  # next state has no action -> value 0
        self.buf.push((s, a, r, s2, done))

    def update(self) -> float | None:
        pc = self.pc
        self.steps += 1
        if len(self.buf) < max(pc.warmup, pc.batch):
            return None
        beta = pc.per_beta0 + (1 - pc.per_beta0) * min(1.0, self.steps / self.total)
        idx, batch, w = self.buf.sample(pc.batch, beta)
        s = collate([b[0] for b in batch], self.device, self.tables)
        a = torch.as_tensor([b[1] for b in batch], device=self.device)
        r = torch.as_tensor([b[2] for b in batch], dtype=torch.float32, device=self.device)
        d = torch.as_tensor([b[4] for b in batch], dtype=torch.float32, device=self.device)
        self.q.train()
        qsa = self.q(s).gather(1, a.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            nxt = [b[3] if b[3] is not None else b[0] for b in batch]
            s2 = collate(nxt, self.device, self.tables)
            a2 = self.q(s2).argmax(1, keepdim=True)
            q2 = self.qt(s2).gather(1, a2).squeeze(1)
            q2 = torch.where(s2["na"] > 0, q2, torch.zeros_like(q2))
            y = r + pc.gamma * q2 * (1 - d)
        td = y - qsa
        loss = (torch.as_tensor(w, dtype=torch.float32, device=self.device) * F.smooth_l1_loss(qsa, y, reduction="none")).mean()
        self.opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.q.parameters(), 10.0)
        self.opt.step()
        self.buf.update(idx, td.detach().cpu().numpy())
        with torch.no_grad():
            for p, pt in zip(self.q.parameters(), self.qt.parameters()):
                pt.mul_(1 - pc.tau_soft).add_(pc.tau_soft * p)
        self.losses.append(float(loss))
        return float(loss)


def observe(env, pc: PolicyConfig):
    """(state encoding, candidate questions, candidate jobs) for the current env state."""
    qs = env.candidate_questions()
    items = env.top_items(env.cfg.Kv)
    return encode_state(env, qs, items, pc), qs, items


def policy_action(env, agent: DQNAgent, pc: PolicyConfig, greedy: bool, pre=None):
    """Map the agent's choice to an env action. Choosing a job => recommend the job actions sorted by Q (UNICORN)."""
    st, qs, items = pre if pre is not None else observe(env, pc)
    if st["na"] == 0:
        return st, 0, ("rec", items.tolist())
    a, q = agent.act(st, greedy)
    kind, k = st["refs"][a]
    if kind == "j":
        if pc.rec_order == "w":
            return st, a, ("rec", items.tolist()[: env.cfg.K])  # items come sorted by w
        jobs = [(q[i], items[st["refs"][i][1]]) for i in range(st["na"]) if st["refs"][i][0] == "j"]
        jobs.sort(key=lambda x: -x[0])
        return st, a, ("rec", [int(j) for _, j in jobs][: env.cfg.K])
    return st, a, qs[k][0]
