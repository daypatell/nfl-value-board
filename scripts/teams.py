"""
One place to reconcile NFL team abbreviations across data sources.

Every feed spells a few teams differently, and the pipeline's matching code
skips anything it can't map - silently. That made Washington vanish from the
board entirely: ESPN emits "WSH" while data/elo_seed.json is keyed on "WAS",
so update_and_build's `not in state["elo"]` guard dropped all 17 of their
games plus the rating updates their opponents should have received.

Canonical form is whatever data/elo_seed.json uses. Aliases below are only
ones actually observed in a live payload, each labelled with its source.
"""
from __future__ import annotations
from typing import Optional

# alias -> canonical (the spelling data/elo_seed.json uses)
ABBR_ALIASES = {
    "WSH": "WAS",  # ESPN scoreboard
    "JAC": "JAX",  # CLEATZ odds-movers
    "LA": "LAR",   # CLEATZ odds-movers (Rams)
}


def normalize_abbr(abbr: Optional[str]) -> Optional[str]:
    """Map a feed's abbreviation to our canonical one. Unknown values pass through."""
    if abbr is None:
        return None
    key = abbr.strip().upper()
    return ABBR_ALIASES.get(key, key)
