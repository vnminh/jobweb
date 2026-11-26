"""Fast text normalisation used for EDA and duplicate detection (no BeautifulSoup: speed)."""

from __future__ import annotations

import hashlib
import html
import re

_TAG_RE = re.compile(r"<[^>]{0,2000}>")
_HAS_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][a-zA-Z0-9]*[^>]{0,2000}>")
_ENTITY_RE = re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{1,6}|#x[0-9a-fA-F]{1,6});")
_LITERAL_ESC_RE = re.compile(r"\\[rnt]")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_WS_RE = re.compile(r"\s+")


def has_html_tag(s: str) -> bool:
    """True if s contains something that looks like an HTML tag."""
    return bool(_HAS_TAG_RE.search(s))


def has_entity(s: str) -> bool:
    """True if s contains an HTML entity such as &nbsp; or &#39;."""
    return bool(_ENTITY_RE.search(s))


def strip_html_fast(s: str) -> str:
    """Remove tags, literal \\r/\\n/\\t escapes and entities; collapse whitespace (keeps case/punctuation)."""
    s = _LITERAL_ESC_RE.sub(" ", s)
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    s = s.replace("\xa0", " ")
    return _WS_RE.sub(" ", s).strip()


def normalize_for_dup(s: str) -> str:
    """Aggressive normalisation for duplicate keys: strip HTML, lowercase, keep only [a-z0-9] tokens."""
    return _NON_ALNUM_RE.sub(" ", strip_html_fast(s).lower()).strip()


def hash64(s: str) -> int:
    """Stable signed 64-bit hash of a string."""
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little", signed=True)
