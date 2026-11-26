"""Simple job fields by regex/keywords (DESIGN 4.2-4.3): seniority, job type, required degree, required years,
salary mention. Each extractor returns None when nothing is found (no guessing)."""

from __future__ import annotations

import re

SENIORITY_LEVELS = ["entry", "mid", "senior", "manager", "executive"]
SENIORITY_ORD = {s: i for i, s in enumerate(SENIORITY_LEVELS)}
JOB_TYPES = ["full_time", "part_time", "contract", "temporary", "internship"]
DEGREE_LEVELS = {0: "None", 1: "High School", 2: "Vocational", 3: "Associate's", 4: "Bachelor's", 5: "Master's", 6: "PhD"}

_T_EXEC = re.compile(r"\b(?:chief|ceo|cfo|coo|cto|cio|cmo|vice[- ]president|vp|svp|evp|avp|president|director|head of|executive director|partner|principal owner)\b", re.I)
_T_MGR = re.compile(r"\b(?<!case )(?<!care )(?<!property )(?:manager|mgr|supervisor|superintendent|foreman|forman|team lead(?:er)?|lead(?:er)?|branch manager|store manager|chef de cuisine|head chef|charge nurse)\b", re.I)
_T_SENIOR = re.compile(r"\b(?:senior(?! (?:care|living|citizens?|home|center|services|housing|community))|sr\.?|principal|expert|architect|iii|iv|level 3|level iii|specialist ii|journeyman|master electrician|master plumber)\b", re.I)
_T_ENTRY = re.compile(r"\b(?:junior|jr\.?|entry[- ]level|entry|trainee|apprentice|intern|internship|assistant|aide|helper|associate|clerk|level 1|level i|i)\b|\b(?:new grad(?:uate)?|graduate program)\b", re.I)
_T_MID = re.compile(r"\b(?:ii|level 2|level ii|intermediate|mid[- ]level)\b", re.I)

_JT = {
    "internship": re.compile(r"\b(?:intern|internship|co-op|coop student)\b", re.I),
    "part_time": re.compile(r"\b(?:part[- ]time|part time|p/t|pt position)\b", re.I),
    "temporary": re.compile(r"\b(?:temporary|temp(?:[- ]to[- ](?:hire|perm))?|seasonal|per diem|prn)\b", re.I),
    "contract": re.compile(r"\b(?:contract[- ]to[- ](?:hire|perm)|c2h|corp[- ]to[- ]corp|1099|w-?2 contract|contract (?:position|role|assignment|opportunity|job|basis|employee|consultant|work|engagement)|(?:short|long)[- ]term contract|on a contract|classification:\s*contract|\d+\+?[- ]months? contract|contract (?:length|duration))\b", re.I),
    "full_time": re.compile(r"\b(?:full[- ]time|full time|f/t|permanent position|direct hire)\b", re.I),
}

_DEG = [
    (6, re.compile(r"\b(?:ph\.?\s?d|doctorate|doctoral|m\.?d\.?|pharm\.?\s?d|j\.?d\.?|d\.?o\.?|dds|dmd|psy\.?d)\b", re.I)),
    (5, re.compile(r"\b(?:master'?s?|masters degree|m\.?s\.?|m\.?a\.?|mba|m\.?b\.?a\.?|msn|mph|msw|m\.?ed|graduate degree)\b", re.I)),
    (4, re.compile(r"\b(?:bachelor'?s?|bachelors|b\.?s\.?|b\.?a\.?|bsn|bsee|bsme|bba|four[- ]year degree|4[- ]year degree|undergraduate degree|college degree|university degree)\b", re.I)),
    (3, re.compile(r"\b(?:associate'?s? degree|associates degree|associate degree|a\.?a\.?s?\.?|a\.?s\.? degree|two[- ]year degree|2[- ]year degree|adn)\b", re.I)),
    (2, re.compile(r"\b(?:vocational|trade school|technical school|certificate program|technical certificate)\b", re.I)),
    (1, re.compile(r"\b(?:high school|h\.?s\.? diploma|ged|g\.?e\.?d\.?|diploma or equivalent)\b", re.I)),
]
_DEG_CONTEXT = re.compile(r"\b(?:degree|diploma|education|graduate|graduated|university|college|accredited)\b", re.I)

_YEARS = re.compile(
    r"(?:(?:minimum|min\.?|at least|over|more than)\s+(?:of\s+)?)?"
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen)\s*(?:\+|plus)?\s*"
    r"(?:(?:-|to|–)\s*(\d{1,2})\s*\+?\s*)?(?:years?|yrs?\.?)\b"
    r"(?:\s+of)?(?:\s+[a-z/&,-]+){0,6}?\s+(?:experience|exp\b|work history)", re.I)
_NUMWORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
             "ten": 10, "twelve": 12, "fifteen": 15}

_SALARY = re.compile(r"\$\s?\d{1,3}(?:,\d{3})+|\$\s?\d+(?:\.\d{2})?\s*(?:k\b|/?\s*(?:hr|hour|an hour|per hour|yr|year|annually))|\$\s?\d{2}\.\d{2}|\b(?!40[13]k)\d{2,3}k\b", re.I)


def seniority_from_title(title: str) -> str | None:
    """Seniority from title keywords only (None if no cue)."""
    t = title or ""
    if _T_EXEC.search(t):
        return "executive"
    if _T_MGR.search(t):
        return "manager"
    if _T_SENIOR.search(t):
        return "senior"
    if _T_MID.search(t):
        return "mid"
    if _T_ENTRY.search(t):
        return "entry"
    return None


def seniority_from_years(years: float | None) -> str | None:
    if years is None:
        return None
    if years <= 1:
        return "entry"
    if years <= 4:
        return "mid"
    return "senior"


def job_seniority(title: str, years_required: float | None) -> tuple[str | None, str]:
    """Combine title cue (priority) and required years. Returns (level, source)."""
    s = seniority_from_title(title)
    if s is not None:
        return s, "title"
    s = seniority_from_years(years_required)
    return (s, "years") if s else (None, "none")


_DIRECT = re.compile(r"\b(?:direct[- ]hire|permanent position|permanent full[- ]time|classification:\s*full[- ]time)\b", re.I)


def job_types(text: str) -> list[str]:
    """All job types mentioned (title + text); 'direct_hire' marks an explicit permanent/direct-hire classification."""
    out = [k for k, r in _JT.items() if r.search(text or "")]
    if _DIRECT.search(text or ""):
        out.append("direct_hire")
    return out


def primary_job_type(types: list[str]) -> str | None:
    """Single categorical value: the most specific type mentioned (internship > part-time > temporary > contract > full-time)."""
    for k in ("internship", "part_time", "temporary"):
        if k in types:
            return k
    if "direct_hire" in types and "full_time" in types:
        return "full_time"
    for k in ("contract", "full_time"):
        if k in types:
            return k
    return None


def required_degree(text: str) -> int | None:
    """Minimum degree level mentioned with a degree/education context (None if no mention)."""
    found = []
    for lvl, r in _DEG:
        for m in r.finditer(text or ""):
            ctx = text[max(0, m.start() - 60):m.end() + 60]
            # short abbreviations (BS, MS, MA, BA, MD, DO, AA, AS) need an education context word nearby
            tok = m.group(0).replace(".", "").replace(" ", "")
            if len(tok) <= 4 and tok.lower() not in ("bsn", "msn", "mba", "phd", "ged", "msw", "mph", "bsee", "bsme", "pharmd", "psyd"):
                ctx30 = text[max(0, m.start() - 30):m.end() + 30]
                after = text[m.end():m.end() + 16]
                field_cue = bool(re.match(r"\s*(?:in|of)\s+[A-Z][a-z]", after)) or bool(re.match(r"\s*/\s*[BM]\.?[ASE]", after))
                if not tok.isupper() or not (_DEG_CONTEXT.search(ctx30) or field_cue):
                    continue
            found.append(lvl)
            break
    return min(found) if found else None


def required_years(text: str) -> float | None:
    """Minimum years of experience required (0-30), from patterns like '3+ years of experience', 'minimum 2-5 years'."""
    vals = []
    for m in _YEARS.finditer(text or ""):
        a = m.group(1).lower()
        v = _NUMWORDS.get(a, None) if not a.isdigit() else int(a)
        if v is not None and 0 <= v <= 30:
            vals.append(v)
    return float(min(vals)) if vals else None


def mentions_salary(text: str) -> bool:
    return bool(_SALARY.search(text or ""))


def user_seniority(years_exp: float | None, managed_others: bool | None, last_title: str | None) -> str | None:
    """User's current seniority: management cue in last title / ManagedOthers, else from years of experience."""
    s = seniority_from_title(last_title or "")
    if s in ("executive", "manager"):
        return s
    if managed_others:
        return "manager"
    if years_exp is None:
        return s
    by_years = "entry" if years_exp <= 1 else "mid" if years_exp <= 4 else "senior"
    return s if s == "senior" else by_years
