"""Rule-based user simulator (DESIGN 9.2-9.3).

Ground truth for a session = target job set V*. n_p = share of target jobs having attribute p.
Answers:
  binary(p)      yes if n_p >= tau, 'whatever' if 0 < n_p < tau, no if n_p == 0
  choice(M)      {x in M : n_x > 0}  (empty -> none)
  hier(M)        same as choice over parent nodes (a parent is accepted if any child has n > 0 == n_parent > 0)
  range(ordinal) smallest [lo, hi] covering the levels of target jobs with a known level ('whatever' if none known)
  confirm(state) yes if the majority of targets are in that state, else the most common target state
  recommend(L)   accept if L contains a target (returns rank of the first target)
Noise: with prob eps an answer is replaced by 'whatever' or flipped (50/50).
Realism: a skill unrelated to the user's past occupations is answered 'whatever' with prob p_unknown_skill.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

YES, NO, WHATEVER = "yes", "no", "whatever"


@dataclass
class SimConfig:
    tau: float = 0.5
    eps: float = 0.0
    p_unknown_skill: float = 0.0
    seed: int = 0


@dataclass
class UserSimulator:
    world: object
    targets: list[int]
    cfg: SimConfig
    known_skills: set[int] = field(default_factory=set)
    rng: np.random.Generator = None

    def __post_init__(self):
        self.rng = self.rng or np.random.default_rng(self.cfg.seed)
        rows = self.world.A[self.targets]
        cnt = np.asarray(rows.sum(0)).ravel()
        nz = np.flatnonzero(cnt)
        self.n = dict(zip(nz.tolist(), (cnt[nz] / len(self.targets)).tolist()))
        self.target_set = set(self.targets)
        self.skill_t = self.world.types.index("skill") if "skill" in self.world.types else -1

    def n_p(self, a: int) -> float:
        return self.n.get(int(a), 0.0)

    def _noisy(self, ans):
        if self.cfg.eps > 0 and self.rng.random() < self.cfg.eps:
            if self.rng.random() < 0.5:
                return WHATEVER
            if ans == YES:
                return NO
            if ans == NO:
                return YES
            return WHATEVER
        return ans

    def _unknown_skill(self, a: int) -> bool:
        return (self.cfg.p_unknown_skill > 0 and self.world.attr_type[a] == self.skill_t and a not in self.known_skills
                and self.rng.random() < self.cfg.p_unknown_skill)

    def binary(self, a: int) -> str:
        if self._unknown_skill(a):
            return WHATEVER
        n = self.n_p(a)
        ans = YES if n >= self.cfg.tau else (WHATEVER if n > 0 else NO)
        return self._noisy(ans)

    def choice(self, options: list[int]) -> list[int] | str:
        if options and all(self._unknown_skill(a) for a in options[:1]):
            return WHATEVER
        acc = [a for a in options if self.n_p(a) > 0]
        if self.cfg.eps > 0 and self.rng.random() < self.cfg.eps:
            if self.rng.random() < 0.5:
                return WHATEVER
            acc = [a for a in options if a not in acc]  # flipped answer
        return acc

    def hier(self, parents: list[int]) -> list[int] | str:
        return self.choice(parents)

    def range(self, levels_of_targets: np.ndarray) -> tuple[int, int] | str:
        lv = levels_of_targets[levels_of_targets >= 0]
        if len(lv) == 0:
            return WHATEVER
        ans = (int(lv.min()), int(lv.max()))
        if self.cfg.eps > 0 and self.rng.random() < self.cfg.eps:
            return WHATEVER
        return ans

    def confirm(self, state_attr: int, target_states: np.ndarray) -> str | int:
        ts = target_states[target_states >= 0]
        if len(ts) == 0:
            return YES
        share = float((ts == state_attr).mean())
        if share >= 0.5:
            return self._noisy(YES) if self.cfg.eps else YES
        return int(Counter(ts.tolist()).most_common(1)[0][0])

    def recommend(self, jobs: list[int]) -> int | None:
        for k, j in enumerate(jobs):
            if j in self.target_set:
                return k + 1
        return None
