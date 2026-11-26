"""P2 cleaning helpers: HTML -> text, boilerplate split, profile normalisation, geo."""

from __future__ import annotations

import html
import re

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ job text

_LITERAL_ESC_RE = re.compile(r"\\[rnt]")
_BLOCK_TAG_RE = re.compile(r"<\s*(?:br|/p|p|/li|li|/div|div|/tr|tr|/h[1-6]|h[1-6]|/ul|ul|/ol|ol)\b[^>]{0,500}>", re.I)
_TAG_RE = re.compile(r"<[^<>]{0,2000}>")
_HTML_TAG_CHECK_RE = re.compile(r"<\s*/?\s*[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?/?\s*>")
_SPACE_RE = re.compile(r"[ \t\f\v\xa0​]+")
_NL_RE = re.compile(r"\s*\n\s*")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.S | re.I)


def clean_html(s: str | None) -> str:
    """HTML/escaped text -> plain text. Keeps line breaks (block tags) as '\\n'; idempotent on clean text.

    Steps: literal '\\r' escapes -> newline; drop comments/script/style; block tags -> newline; strip tags;
    unescape entities (twice: '&amp;nbsp;' occurs); strip tags again (entities may decode to '<b>');
    normalise whitespace.
    """
    if not s:
        return ""
    s = _LITERAL_ESC_RE.sub("\n", s)
    s = _COMMENT_RE.sub(" ", s)
    s = _STYLE_RE.sub(" ", s)
    for _ in range(2):
        s = _BLOCK_TAG_RE.sub("\n", s)
        s = _TAG_RE.sub(" ", s)
        s = html.unescape(s)
    s = _BLOCK_TAG_RE.sub("\n", s)
    s = _TAG_RE.sub(" ", s)
    s = s.replace("\r", "\n")
    s = _SPACE_RE.sub(" ", s)
    s = _NL_RE.sub("\n", s)
    return s.strip()


def has_html_tag(s: str) -> bool:
    """Regex check used for the P2 acceptance test (0 tags left)."""
    return bool(_HTML_TAG_CHECK_RE.search(s or ""))


_BOILER_PATTERNS = [
    r"equal opportunity employer", r"\beoe\b", r"\baa/eoe\b", r"m/f/d/v", r"affirmative action",
    r"drug[- ]free workplace", r"background check", r"without regard to (race|age|sex)",
    r"click (here|the apply)", r"apply (now|online|today)", r"to apply,? (please|send|visit|click)",
    r"send (your )?resume", r"e-?mail (your )?resume", r"visit (us|our website)", r"www\.", r"https?://",
    r"about (us|the company)\b", r"is an? (leading|premier|national|global)", r"founded in \d{4}",
    r"\ball qualified applicants\b", r"job (number|id|code)\s*[:#]", r"reference (number|code)",
]
_BOILER_RE = re.compile("|".join(_BOILER_PATTERNS), re.I)


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


def split_boilerplate(text: str) -> tuple[str, str]:
    """Split cleaned text into (core, boilerplate) by sentence-level rules (EEO, how-to-apply, company blurb).

    Lines are split into sentences first, so a one-paragraph posting that ends with "apply online" only loses
    that sentence.
    """
    core_lines, boiler = [], []
    for line in text.split("\n"):
        kept = []
        for sent in _SENT_SPLIT_RE.split(line):
            (boiler if _BOILER_RE.search(sent) else kept).append(sent)
        if kept:
            core_lines.append(" ".join(kept))
    return "\n".join(core_lines).strip(), " ".join(boiler).strip()


_TITLE_JUNK_RE = re.compile(r"[^\w\s/&+#.\-]")
_WS_RE = re.compile(r"\s+")


def normalize_title(t: str | None) -> str:
    """Lowercase title, unescape, drop junk chars, collapse whitespace."""
    if not t:
        return ""
    t = html.unescape(_TAG_RE.sub(" ", t)).lower()
    t = _TITLE_JUNK_RE.sub(" ", t)
    return _WS_RE.sub(" ", t).strip(" -./")


# ------------------------------------------------------------------ users

DEGREE_ORDINAL = {
    "None": 0, "High School": 1, "Vocational": 2, "Associate's": 3, "Bachelor's": 4, "Master's": 5, "PhD": 6,
}
DEGREE_NAMES = {v: k for k, v in DEGREE_ORDINAL.items()}
MAX_PLAUSIBLE_EXPERIENCE = 50


def clean_major(m: str | None) -> str | None:
    """Lowercase, drop punctuation, collapse whitespace; None for empty / 'none' / 'n/a'."""
    if m is None or (isinstance(m, float) and np.isnan(m)) or m is pd.NA:
        return None
    m = _WS_RE.sub(" ", re.sub(r"[^a-z0-9&/+ ]", " ", str(m).lower())).strip()
    return None if m in ("", "none", "na", "n a", "n/a", "no", "-") else m


def clean_experience(x: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return (years, flag_bad): values > MAX_PLAUSIBLE_EXPERIENCE or < 0 -> NA (flagged)."""
    x = pd.to_numeric(x, errors="coerce")
    bad = (x > MAX_PLAUSIBLE_EXPERIENCE) | (x < 0)
    return x.mask(bad).astype("Float64"), bad.fillna(False)


def yes_no(s: pd.Series) -> pd.Series:
    return s.map({"Yes": True, "No": False}).astype("boolean")


# ------------------------------------------------------------------ geo

def zip5(s: pd.Series) -> pd.Series:
    """Normalise ZIP strings to 5 digits ('60601-1234' -> '60601', '501' -> '00501'); invalid -> NA."""
    z = s.astype("string").str.extract(r"^\s*(\d{3,5})", expand=False)
    return z.str.zfill(5)


def norm_city(s: pd.Series) -> pd.Series:
    """City key: lowercase, '.'/'-' removed, 'saint'/'st' unified, whitespace collapsed."""
    c = s.astype("string").str.lower().str.replace(r"[.\-']", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    c = c.str.replace(r"^saint ", "st ", regex=True).str.replace(r"^ft ", "fort ", regex=True).str.replace(r"^mt ", "mount ", regex=True)
    return c


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Great-circle distance in km (vectorised, inputs in degrees)."""
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(a, dtype=float)) for a in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


class Geocoder:
    """ZIP -> (lat, lon); fallback City|State -> mean of ZIP centroids; fallback State centroid.

    Built from GeoNames US postal codes (data/external/geonames/US.txt, CC BY 4.0).
    """

    def __init__(self, geonames_path: str):
        g = pd.read_csv(geonames_path, sep="\t", header=None, dtype=str, keep_default_na=False,
                        names=["country", "zip", "place", "state_name", "state", "county", "county_code",
                               "c3", "c3code", "lat", "lon", "acc"])
        g["lat"] = pd.to_numeric(g["lat"], errors="coerce")
        g["lon"] = pd.to_numeric(g["lon"], errors="coerce")
        g = g.dropna(subset=["lat", "lon"])
        self.by_zip = g.drop_duplicates("zip").set_index("zip")[["lat", "lon"]]
        g["city_key"] = norm_city(g["place"]) + "|" + g["state"].str.upper()
        self.by_city = g.groupby("city_key")[["lat", "lon"]].mean()
        self.by_state = g.groupby(g["state"].str.upper())[["lat", "lon"]].mean()

    def geocode(self, zips: pd.Series, cities: pd.Series, states: pd.Series) -> pd.DataFrame:
        """Return DataFrame(lat, lon, geo_source in {zip, city, state, none}) aligned to input index."""
        z = zip5(zips)
        st = states.astype("string").str.upper().str.strip()
        ck = norm_city(cities) + "|" + st
        out = pd.DataFrame(index=zips.index, columns=["lat", "lon"], dtype=float)
        src = pd.Series("none", index=zips.index, dtype="object")
        for key, table, name in ((z, self.by_zip, "zip"), (ck, self.by_city, "city"), (st, self.by_state, "state")):
            need = out["lat"].isna()
            if not need.any():
                break
            k = key[need]
            lat = k.map(table["lat"])
            lon = k.map(table["lon"])
            hit = lat.notna()
            idx = hit[hit].index
            out.loc[idx, "lat"] = lat[hit].astype(float)
            out.loc[idx, "lon"] = lon[hit].astype(float)
            src.loc[idx] = name
        out["geo_source"] = src
        return out
