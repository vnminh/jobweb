"""Rule-based conversational policies (DESIGN 11.3) + oracle/random sanity policies."""

from __future__ import annotations

import numpy as np


class AbsGreedy:
    """Only recommends: top-K by current score every turn (Christakopoulou+16)."""

    name = "abs_greedy"

    def act(self, env) -> tuple:
        return ("rec", env.top_items(env.cfg.K).tolist())


class MaxEntropy:
    """Asks the best-scored question (weighted entropy / EIG per env config); recommends when the candidate set is
    small (<= rec_threshold), when no question is left, or at the last turn."""

    name = "max_entropy"

    def __init__(self, rec_threshold: int = 50):
        self.rec_threshold = rec_threshold

    def act(self, env) -> tuple:
        if len(env.cand) <= self.rec_threshold or env.t >= env.cfg.T - 1:
            return ("rec", env.top_items(env.cfg.K).tolist())
        qs = env.candidate_questions()
        if not qs:
            return ("rec", env.top_items(env.cfg.K).tolist())
        return qs[0][0]


class EIGThreshold:
    """Heuristic of DESIGN 10 S4: ask the top-scored (EIG) question unless the belief mass of the top-K list exceeds a
    threshold; after `ask_budget` questions it only recommends (soft constraints never shrink the candidate set, so a
    candidate-count rule like Max Entropy would ask until the last turn)."""

    name = "eig_threshold"

    def __init__(self, mass_threshold: float = 0.1, ask_budget: int = 4):
        self.mass_threshold, self.ask_budget = mass_threshold, ask_budget

    def act(self, env) -> tuple:
        top = env.top_items(env.cfg.K)
        mass = float(env.b[np.isin(env.cand, top)].sum()) if len(top) else 1.0
        n_asked = sum(1 for h in env.history if h["action"][0] not in ("rec", "init"))
        if mass >= self.mass_threshold or n_asked >= self.ask_budget or env.t >= env.cfg.T - 1:
            return ("rec", top.tolist())
        qs = env.candidate_questions()
        return qs[0][0] if qs else ("rec", top.tolist())


class RandomPolicy:
    """Uniform over the action candidate set (top-Kq questions + recommend)."""

    name = "random"

    def __init__(self, seed: int = 0):
        self.rng = np.random.default_rng(seed)

    def act(self, env) -> tuple:
        qs = env.candidate_questions()
        i = self.rng.integers(0, len(qs) + 1)
        if i == len(qs):
            cand = env.cand
            k = min(env.cfg.K, len(cand))
            return ("rec", self.rng.choice(cand, size=k, replace=False).tolist() if k else [])
        return qs[i][0]


class Oracle:
    """Knows the targets: recommends a list containing a reachable target at turn 1 (sanity upper bound)."""

    name = "oracle"

    def act(self, env) -> tuple:
        reach = [j for j in env.sim.targets if j in set(env.cand.tolist())]
        top = env.top_items(env.cfg.K).tolist()
        if reach:
            return ("rec", [reach[0]] + [j for j in top if j != reach[0]][: env.cfg.K - 1])
        return ("rec", top)
