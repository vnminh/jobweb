"""Job title -> O*NET occupation mapping by embedding similarity (DESIGN 4.3).

1. clean the title for mapping (drop location, salary, shift, req-codes, hiring noise);
2. exact match against O*NET title/alternate/reported labels when the label maps to a single code;
3. otherwise cosine similarity between the title embedding and all label embeddings (FAISS inner product);
   code score = max over its labels; keep top-k codes;
4. optional re-rank of low-confidence titles with (title + description snippet) vs occupation description.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from jobunicorn.attributes.onet import Onet
from jobunicorn.data.clean import normalize_title

_STATE = r"(?:A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOT]|N[EVHJMYCD]|O[HKR]|PA|RI|S[CD]|T[NX]|UT|V[TA]|W[AVIY])"
_NOISE_PATTERNS = [
    rf"\b(?:in\s+)?[A-Z][A-Za-z.]+(?:\s[A-Z][A-Za-z.]+){{0,3}},\s*{_STATE}\b(?:\s*\d{{5}})?",  # City, ST
    rf"\s[-–|/]\s*{_STATE}\b.*$",  # " - IL ..."
    r"\$\s?\d[\d,.]*\s*(?:k|K)?(?:\s*(?:-|to)\s*\$?\s?\d[\d,.]*\s*(?:k|K)?)?(?:\s*(?:/|per)\s*(?:hr|hour|yr|year))?",
    r"\b\d{2,3}k\b",
    r"\b(?:req|job|ref|requisition|id)\s*(?:#|no\.?|number)?\s*[:#]?\s*[A-Z0-9-]{3,}\b",
    r"#\s*[A-Z0-9-]+",
    r"\b(?:urgent(?:ly)?|immediate(?:ly)?|now hiring|hiring|needed|wanted|opening|openings|opportunity|position|job|jobs|apply now|asap|hot)\b",
    r"\b(?:full[- ]?time|part[- ]?time|f/t|p/t|ft|pt|temp(?:orary)?(?:[- ]to[- ]hire)?|contract(?:[- ]to[- ]hire)?|c2h|per diem|prn|seasonal)\b",
    r"\b(?:1st|2nd|3rd|first|second|third|day|night|evening|weekend|overnight|graveyard)s?\s*(?:shift)?s?\b",
    r"\b(?:shift|shifts|weekends?|nights?)\b",
    r"\b(?:sign[- ]on bonus|bonus|benefits|relocation|remote|telecommute|work from home)\b",
]
_NOISE_RE = [re.compile(p, re.I if i >= 2 else 0) for i, p in enumerate(_NOISE_PATTERNS)]


def clean_title_for_mapping(title: str | None) -> str:
    """Strip location/salary/shift/hiring noise, then normalise (lowercase). Falls back to plain normalise."""
    if not title:
        return ""
    t = title
    for r in _NOISE_RE:
        t = r.sub(" ", t)
    t = normalize_title(t)
    t = re.sub(r"^[\s\-/&,.]+|[\s\-/&,.]+$", "", t)
    t = re.sub(r"\s*[-/,]\s*[-/,]\s*", " - ", t).strip(" -")
    return t if len(t) >= 2 else normalize_title(title)


class TitleMapper:
    """Map titles to O*NET codes. Embeddings are L2-normalised so inner product = cosine."""

    def __init__(self, onet: Onet, model, batch_size: int = 512, labels: pd.DataFrame | None = None, n_label_hits: int = 50, agg: str = "max"):
        import faiss

        self.onet = onet
        self.model = model
        self.batch_size = batch_size
        labs = onet.labels if labels is None else labels
        g = labs.groupby("label_norm")["code"].agg(lambda s: sorted(set(s)))
        self.label_text = g.index.tolist()
        self.label_codes = g.tolist()
        self.exact = {t: c[0] for t, c in zip(self.label_text, self.label_codes) if len(c) == 1}
        self.codes = sorted(set(onet.occupations["code"]))
        self.code_idx = {c: i for i, c in enumerate(self.codes)}
        # label -> list of code indices
        self.label_code_idx = [[self.code_idx[c] for c in cs if c in self.code_idx] for cs in self.label_codes]
        emb = self.encode(self.label_text)
        self.index = faiss.IndexFlatIP(emb.shape[1])
        self.index.add(emb)
        self.n_label_hits = n_label_hits
        self.agg = agg  # 'max' | 'top3mean': mean of a code's 3 best label sims (missing -> 0.8 * best)

    def encode(self, texts: list[str]) -> np.ndarray:
        e = self.model.encode(texts, batch_size=self.batch_size, convert_to_numpy=True, normalize_embeddings=True,
                              show_progress_bar=False)
        return e.astype(np.float32)

    def map(self, titles: list[str], k: int = 5, use_exact: bool = True) -> pd.DataFrame:
        """Return DataFrame: query, method, code_1..k, score_1..k (cosine; exact match = 1.0)."""
        q = list(titles)
        emb = self.encode(q) if q else np.zeros((0, self.index.d), dtype=np.float32)
        D, I = self.index.search(emb, self.n_label_hits)
        rows = []
        for qi, t in enumerate(q):
            hits: dict[int, list[float]] = {}
            for s, li in zip(D[qi], I[qi]):
                if li < 0:
                    continue
                for ci in self.label_code_idx[li]:
                    hits.setdefault(ci, []).append(float(s))
            if self.agg == "top3mean":
                best = {}
                for ci, v in hits.items():
                    v = sorted(v, reverse=True)[:3]
                    v = v + [0.8 * v[0]] * (3 - len(v))
                    best[ci] = 0.6 * v[0] + 0.4 * (sum(v[1:]) / 2)
            else:
                best = {ci: max(v) for ci, v in hits.items()}
            top = sorted(best.items(), key=lambda x: -x[1])[:k]
            method = "emb"
            if use_exact and t in self.exact:
                c = self.code_idx[self.exact[t]]
                top = [(c, 1.0)] + [x for x in top if x[0] != c][: k - 1]
                method = "exact"
            r = {"query": t, "method": method}
            for j in range(k):
                r[f"code_{j + 1}"] = self.codes[top[j][0]] if j < len(top) else None
                r[f"score_{j + 1}"] = top[j][1] if j < len(top) else np.nan
            rows.append(r)
        return pd.DataFrame(rows)


def holdout_eval(onet: Onet, model, n: int = 3000, seed: int = 0, batch_size: int = 512, agg: str = "max") -> dict:
    """Leave-out check of an encoder: hold out n alternate/reported labels that map to a single code (and whose exact
    string is removed from the label index), map them back, report code/group accuracy@1 and @5."""
    labs = onet.labels
    single = labs.groupby("label_norm")["code"].nunique()
    cand = labs[labs["source"].isin(["alternate", "reported"]) & labs["label_norm"].map(single).eq(1)].drop_duplicates("label_norm")
    held = cand.sample(n=min(n, len(cand)), random_state=seed)
    rest = labs[~labs["label_norm"].isin(set(held["label_norm"]))]
    tm = TitleMapper(onet, model, batch_size=batch_size, labels=rest, agg=agg)
    res = tm.map(held["label_norm"].tolist(), k=5, use_exact=False)
    gold = held["code"].to_numpy()
    top1 = res["code_1"].to_numpy()
    top5 = res[[f"code_{j}" for j in range(1, 6)]].to_numpy()
    return {
        "n": int(len(held)),
        "code_acc@1": float(np.mean(top1 == gold)),
        "code_acc@5": float(np.mean([g in row for g, row in zip(gold, top5)])),
        "group_acc@1": float(np.mean([str(a)[:2] == str(b)[:2] for a, b in zip(top1, gold)])),
    }
