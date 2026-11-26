"""Skill extraction by dictionary matching (DESIGN 4.3).

Dictionary = O*NET Technology Skills examples (with vendor-stripped aliases) + curated lexicon.
Matching uses an Aho-Corasick automaton over lower-cased text with word-boundary checks.

Method A (baseline): every alias match counts.
Method B (improved): ambiguous aliases (common words / short tokens) only count when a tech context cue is
nearby AND the original text is not all-lowercase; blacklisted aliases never count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from jobunicorn.attributes.skill_lexicon import (
    AMBIGUOUS_ALIASES, BLACKLIST_ALIASES, CURATED_SKILLS, NEGATIVE_CONTEXT, TECH_CONTEXT_CUES,
)

_VENDORS = [
    "microsoft", "ms", "adobe", "oracle", "ibm", "sap", "google", "apple", "autodesk", "intuit", "salesforce.com",
    "salesforce", "amazon", "cisco", "sas", "red hat", "vmware", "citrix", "symantec", "mcafee", "corel", "hp",
    "hewlett packard", "dell", "novell", "sybase", "teradata", "informatica", "tibco", "bentley", "dassault systemes",
    "ptc", "siemens", "esri", "epic systems", "cerner", "mckesson", "allscripts", "sage", "infor", "the mathworks",
    "mathworks", "wolfram research", "minitab", "spss", "ibm spss", "atlassian", "jetbrains", "embarcadero", "quest",
    "ca", "bmc", "bmc software", "blackbaud", "kronos", "adp", "workday", "netsuite", "meditech", "open text",
    "opentext", "hyland", "laserfiche", "esri arcgis", "trimble", "ansys", "mentor graphics", "cadence", "synopsys",
    "national instruments", "rockwell", "rockwell automation", "allen bradley", "schneider electric", "ge", "honeywell",
]
_VENDOR_RE = re.compile(r"^(?:" + "|".join(re.escape(v) for v in sorted(_VENDORS, key=len, reverse=True)) + r")\s+")
_SUFFIX_RE = re.compile(r"\s+(?:software|system|systems|application|applications|suite|platform)$")
_WORD_RE = re.compile(r"[a-z0-9]")


@dataclass
class SkillDict:
    skills: pd.DataFrame  # skill_id, name, source ('onet_tech' | 'curated'), hot (bool)
    aliases: pd.DataFrame  # alias, skill_id, ambiguous (bool)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


_GENERIC_EXAMPLE_RE = re.compile(r"^[A-Z][a-z]+(?: [a-z]+)* (?:software|systems?|applications?)$")
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*")


def lowercase_ratio(texts, vocab: set[str]) -> dict[str, float]:
    """For each single-token alias in vocab: share of its corpus occurrences written all-lowercase.
    High ratio => ordinary English word (e.g. 'inventory'), low => product name (e.g. 'QuickBooks', 'AutoCAD')."""
    from collections import Counter

    low, tot = Counter(), Counter()
    for t in texts:
        for tok in _TOKEN_RE.findall(t or ""):
            tok = tok.rstrip(".")
            k = tok.lower()
            if k in vocab:
                tot[k] += 1
                if tok.islower():
                    low[k] += 1
    return {k: low[k] / tot[k] for k in tot}


def build_skill_dict(onet_tech: pd.DataFrame, min_alias_len: int = 2, lower_ratio: dict[str, float] | None = None,
                     common_ratio: float = 0.25) -> SkillDict:
    """Build the skill vocabulary + alias table.

    lower_ratio (from `lowercase_ratio` on a corpus sample) marks single-token aliases that are ordinary words:
    such aliases are dropped when produced by vendor/suffix stripping, and marked ambiguous when they are the full
    example name. Generic O*NET placeholder examples ('Medical software') are skipped.
    """
    lower_ratio = lower_ratio or {}
    derived_single: set[str] = set()

    def common(a: str) -> bool:
        return (" " not in a) and a.isalpha() and lower_ratio.get(a, 0.0) > common_ratio

    rows, alias_rows = [], []
    ex = onet_tech.groupby("example").agg(hot=("hot", lambda s: (s == "Y").any())).reset_index()
    for i, r in enumerate(ex.itertuples(index=False)):
        sid = f"T{i:05d}"
        if _GENERIC_EXAMPLE_RE.match(r.example):
            continue
        rows.append((sid, r.example, "onet_tech", bool(r.hot)))
        full = _norm(r.example)
        forms = {full}
        stripped = _SUFFIX_RE.sub("", _VENDOR_RE.sub("", full)).strip()
        if stripped and stripped != full and not common(stripped):
            forms.add(stripped)
            if " " not in stripped:
                derived_single.add(stripped)
        # trailing acronym in parentheses, e.g. "Structured query language (SQL)"
        m = re.search(r"\(([^)]{2,15})\)\s*$", r.example)
        if m:
            forms.add(_norm(m.group(1)))
        for f in forms:
            alias_rows.append((f, sid))
    for j, (name, forms) in enumerate(CURATED_SKILLS.items()):
        sid = f"C{j:04d}"
        rows.append((sid, name, "curated", False))
        for f in forms:
            alias_rows.append((_norm(f), sid))
    skills = pd.DataFrame(rows, columns=["skill_id", "name", "source", "hot"])
    al = pd.DataFrame(alias_rows, columns=["alias", "skill_id"]).drop_duplicates()
    al = al[(al["alias"].str.len() >= min_alias_len) & ~al["alias"].isin(BLACKLIST_ALIASES)]
    al = al[al["alias"].str.contains(r"[a-z]", regex=True)]
    # alias mapping to several skills: keep curated first, else the shortest skill name (most generic product)
    al = al.merge(skills[["skill_id", "name", "source"]], on="skill_id")
    al["_rank"] = (al["source"] != "curated").astype(int) * 1000 + al["name"].str.len()
    al = al.sort_values(["alias", "_rank"]).drop_duplicates("alias")[["alias", "skill_id", "source"]]
    one_tok = ~al["alias"].str.contains(" ")
    al["ambiguous"] = (al["alias"].isin(AMBIGUOUS_ALIASES)
                       | (one_tok & (al["alias"].str.len() <= 3) & ~al["alias"].str.contains(r"[+#./0-9-]", regex=True))
                       | (al["alias"].map(common) & (al["source"] != "curated"))
                       | (al["alias"].isin(derived_single) & (al["source"] != "curated")))
    # curated phrases were chosen by hand: the corpus common-word rule does not apply to them
    al = al.drop(columns=["source"])
    return SkillDict(skills=skills, aliases=al.reset_index(drop=True))


class SkillMatcher:
    """Aho-Corasick matcher; returns per-text dict skill_id -> (count_A, count_B)."""

    def __init__(self, aliases: pd.DataFrame):
        import ahocorasick

        self.A = ahocorasick.Automaton()
        for a, sid, amb in aliases[["alias", "skill_id", "ambiguous"]].itertuples(index=False):
            self.A.add_word(a, (sid, bool(amb), len(a)))
        self.A.make_automaton()

    @staticmethod
    def _boundary_ok(low: str, s: int, e: int) -> bool:
        before = low[s - 1] if s > 0 else " "
        after = low[e + 1] if e + 1 < len(low) else " "
        return not _WORD_RE.match(before) and not _WORD_RE.match(after)

    def match(self, text: str) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        if not text:
            return out
        low = text.lower()
        if len(low) != len(text):  # rare unicode case-length change: fall back to lower-only checks
            text = low
        for e, (sid, amb, L) in self.A.iter(low):
            s = e - L + 1
            if not self._boundary_ok(low, s, e):
                continue
            cnt = out.setdefault(sid, [0, 0])
            cnt[0] += 1
            alias = low[s:e + 1]
            if alias in NEGATIVE_CONTEXT:
                ctx = low[max(0, s - 50):s] + " " + low[e + 1:e + 51]
                if any(c in ctx for c in NEGATIVE_CONTEXT[alias]):
                    continue
            if amb:
                orig = text[s:e + 1]
                if orig.islower():
                    continue
                ctx = low[max(0, s - 40):s] + " " + low[e + 1:e + 41]  # exclude the alias itself
                if not any(c in ctx for c in TECH_CONTEXT_CUES):
                    continue
            cnt[1] += 1
        return out
