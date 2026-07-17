"""Name-based entity linking for identifier-less items (Convergence-graph §4 / coverage lift).

The linker (``linker.py``) resolves an item only when its source record carries an authoritative
identifier (ticker/CIK/UEI) — EDGAR and USAspending do; **feeds, GDELT and arXiv do not**, so ~75% of
items go unlinked and the convergence graph starves (§1's live run: 215 co-appearances → 1 edge). This
module lifts that ceiling by matching **known reference-entity names as they literally appear in the
item text**, then linking via the resolver's exact path — generalizing the NRC ticker-allowlist pattern
(D096) from a hand-curated handful to the whole seeded reference set.

**Precision is the whole game here** (a wrong link is worse than no link; the resolver is eval-gated to
0.95). Three guards, chosen so a false link is very unlikely rather than merely uncommon:

1. **Multi-word aliases only.** A single-token alias ("BLOCK", "GAP", "CORE", "NU") collides with common
   English; a ≥2-token company name ("LOCKHEED MARTIN", "ENERGY FUELS") effectively does not. Single-token
   names still link via the identifier path when a structured source supplies them — they're just not
   trusted from free text.
2. **Exact word-boundary match**, via token n-grams — never a substring inside another word.
3. **Ambiguity drop.** If one normalized alias maps to two different entities, it's discarded — an
   unresolved mention beats a confidently wrong one (the resolver's own rule).

Pure functions (index build + matching) are unit-tested against fixtures; the DB loader is thin.
"""
from __future__ import annotations

import re

# An alias must have at least this many whitespace tokens to be trusted from free text (guard 1).
_MIN_TOKENS = 2
# Longest alias (in tokens) worth scanning for; caps the n-gram window. Real company names rarely
# exceed this, and it bounds the per-item work regardless of index size.
_MAX_TOKENS = 6
# Normalized multi-word aliases that are still too generic to trust from prose: phrases that are
# ordinary domain language which happens to also be a company name, so they match generically and
# mislink. Curated + additive — the principled signal is document frequency (a real company name is
# rare across items; a generic phrase is everywhere), measured with scripts. The three tech phrases
# below were the clear DF outliers on the live corpus (QUANTUM COMPUTING alone hit 25/1164 items,
# almost all the generic phrase, not the company QUBT; HYPERSCALE DATA is literally an EDGAR probe
# phrase; AI ERA is prose). Kept tiny on purpose — most 2-token company names are safe.
_STOPWORD_ALIASES: frozenset[str] = frozenset({
    "GENERAL PUBLIC",
    "UNITED STATES",
    "NEW AMERICA",
    "OPEN TEXT",
    "QUANTUM COMPUTING",
    "HYPERSCALE DATA",
    "AI ERA",
})


def _normalize_text(text: str) -> list[str]:
    """Uppercase, drop punctuation to spaces, split into word tokens (matches alias normalization)."""
    upper = re.sub(r"[^A-Z0-9]+", " ", (text or "").upper())
    return upper.split()


def build_alias_index(rows: list[tuple[str, str]]) -> dict[str, str]:
    """Build ``{normalized_alias: entity_id}`` from ``(alias_normalized, entity_id)`` rows.

    Keeps only aliases safe to match from free text: ≥ ``_MIN_TOKENS`` tokens, not a stopword. An
    alias that resolves to two *different* entities is ambiguous and dropped entirely (precision-first).
    """
    index: dict[str, str] = {}
    dropped: set[str] = set()
    for alias, entity_id in rows:
        alias = (alias or "").strip()
        if not alias or alias in dropped or alias in _STOPWORD_ALIASES:
            continue
        if len(alias.split()) < _MIN_TOKENS:
            continue
        existing = index.get(alias)
        if existing is not None and existing != entity_id:
            # collision across entities → ambiguous, remove and blacklist
            del index[alias]
            dropped.add(alias)
            continue
        index[alias] = entity_id
    return index


def find_mentions(text: str, index: dict[str, str]) -> list[str]:
    """Return entity_ids whose (multi-word) alias occurs verbatim in ``text``, order-preserving unique.

    Slides token n-grams (length ``_MIN_TOKENS``..``_MAX_TOKENS``) over the normalized text and looks
    each up in the index — exact, word-boundary, O(tokens) per item.
    """
    tokens = _normalize_text(text)
    seen: set[str] = set()
    out: list[str] = []
    n_hi = min(_MAX_TOKENS, len(tokens))
    for i in range(len(tokens)):
        for n in range(_MIN_TOKENS, n_hi + 1):
            if i + n > len(tokens):
                break
            gram = " ".join(tokens[i:i + n])
            entity_id = index.get(gram)
            if entity_id is not None and entity_id not in seen:
                seen.add(entity_id)
                out.append(entity_id)
    return out


async def load_alias_index(conn) -> dict[str, str]:
    """Load the safe multi-word alias index from the active reference set."""
    rows = await conn.fetch(
        "SELECT a.alias_normalized AS alias, a.entity_id::text AS entity_id "
        "FROM entity_aliases a JOIN entities e ON e.id = a.entity_id WHERE e.is_active"
    )
    return build_alias_index([(r["alias"], r["entity_id"]) for r in rows])
