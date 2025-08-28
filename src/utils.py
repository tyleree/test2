import re
from typing import List, Dict

def strip_boilerplate(text: str) -> str:
    """Remove nav, cookie banners, footer cruft by simple heuristics"""
    patt = r"(accept cookies|subscribe|newsletter|footer|copyright|\[advertisement\])"
    return re.sub(patt, "", text, flags=re.IGNORECASE)

def dedupe_preserve_order(items: List[str]) -> List[str]:
    """Deduplicate items while preserving order"""
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out

def clamp(n, lo, hi):
    """Clamp a number between lo and hi"""
    return max(lo, min(n, hi))






