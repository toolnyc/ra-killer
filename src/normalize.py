"""String normalization utilities for dedup and taste matching.

Centralizes all normalization so dedup, taste matching, and display
use the same canonical forms.
"""

from __future__ import annotations

import re
import unicodedata

# ── Performance qualifiers stripped from artist names ──────────────
_ARTIST_QUALIFIERS = re.compile(
    r"\s*\("
    r"(?:live|dj set|dj|hybrid|hybrid live|live set|"
    r"all night long|all night|extended set|closing set|opening set|"
    r"b2b[^)]*)"
    r"\)\s*",
    re.IGNORECASE,
)

# "& friends", "& guests", etc. at end of artist name
_ARTIST_SUFFIX = re.compile(
    r"\s*&\s*(?:friends|guests|more|special guests?)\s*$",
    re.IGNORECASE,
)

# "presents:", "presents" prefix (promoter branding)
_PRESENTS_PREFIX = re.compile(
    r"^.*?\bpresents\s*:?\s*",
    re.IGNORECASE,
)

# b2b / B2B splitting pattern
_B2B_SPLIT = re.compile(r"\s+[Bb]2[Bb]\s+")


def normalize(s: str) -> str:
    """Normalize string for comparison: lowercase, strip accents/punctuation, collapse whitespace."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_venue(s: str) -> str:
    """Normalize a venue name for comparison.

    Beyond base normalize():
    - Strips leading "the "
    - Replaces "&" with "and" before punctuation stripping
    - Strips common suffixes: "ny", "nyc", "brooklyn", "manhattan", "queens"
    - Strips room/zone qualifiers: "- zone one", "- hall", etc.
    """
    # Replace & with 'and' before base normalize strips it
    s = s.replace("&", "and")
    # Strip room/zone qualifiers (e.g. "Elsewhere - Zone One")
    s = re.sub(r"\s*[-–—]\s*(zone\s+\w+|room\s+\w+|hall|studio|stage)\b.*$", "", s, flags=re.IGNORECASE)
    s = normalize(s)
    # Strip leading "the"
    s = re.sub(r"^the\s+", "", s)
    # Strip trailing borough/city qualifiers
    s = re.sub(r"\s+(ny|nyc|brooklyn|bk|manhattan|queens|bushwick|williamsburg|ridgewood)$", "", s)
    return s.strip()


def normalize_artist(s: str) -> str:
    """Normalize an artist name for comparison.

    Beyond base normalize():
    - Strips performance qualifiers: (Live), (DJ Set), (B2B ...), etc.
    - Strips "& friends" / "& guests" suffixes
    - Strips "presents:" prefixes
    """
    # Strip qualifiers before base normalization (they contain parens)
    s = _ARTIST_QUALIFIERS.sub(" ", s)
    s = _ARTIST_SUFFIX.sub("", s)
    s = _PRESENTS_PREFIX.sub("", s)
    return normalize(s)


def split_artist_entry(s: str) -> list[str]:
    """Split a single artist string that may contain multiple artists.

    Handles: "Artist1 b2b Artist2", "Artist1 B2B Artist2"
    Returns list of individual normalized artist names.
    """
    parts = _B2B_SPLIT.split(s)
    if len(parts) > 1:
        return [normalize_artist(p) for p in parts if p.strip()]
    return [normalize_artist(s)]


def normalize_artist_list(artists: list[str]) -> set[str]:
    """Normalize and flatten an artist list, splitting b2b entries."""
    result: set[str] = set()
    for a in artists:
        for name in split_artist_entry(a):
            if name:
                result.add(name)
    return result
