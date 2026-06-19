import re
from dataclasses import dataclass
from enum import Enum

# Thresholds from D027 — overridden by Settings at runtime
_HIGH = 0.92
_MEDIUM = 0.70
_LOW = 0.55

_SUFFIXES = {
    " INC", " CORP", " LLC", " LTD", " LP", " CO",
    " CORPORATION", " INCORPORATED", " LIMITED", " COMPANY",
    " PLC", " GMBH", " AG", " SA",
}


class ResolutionStatus(str, Enum):
    AUTO_LINK = "auto_link"
    LLM_DISAMBIGUATE = "llm_disambiguate"
    LLM_EXPAND_CONTEXT = "llm_expand_context"
    AUTO_DISMISS = "auto_dismiss"


@dataclass
class ResolutionResult:
    status: ResolutionStatus
    entity_id: str | None
    confidence: float
    resolved_by: str | None  # 'auto_high_confidence' | 'llm_auto' | None

    @property
    def is_resolved(self) -> bool:
        return self.entity_id is not None


def normalize_mention(mention: str) -> str:
    upper = mention.upper().strip()
    # SEC titles carry a state-of-incorporation tag like "NORTHROP GRUMMAN CORP /DE/". Strip the
    # slash-delimited jurisdiction code: left in, it pollutes the trigram match AND blocks the
    # suffix strip below, dropping a clean mention ("Northrop Grumman") into the medium band where
    # v1 leaves it unresolved (T3.2 recall fix). The lookbehind avoids mangling an internal slash
    # in a real name (e.g. "AC/DC") — SEC tags are always space-delimited.
    upper = re.sub(r"(?<![A-Z0-9])/[A-Z]{2,5}/?", " ", upper)
    # Drop punctuation (periods/commas) and collapse whitespace so "Apple Inc." and
    # "Palantir, Inc" normalize like "Apple Inc" / "Palantir Inc" — otherwise a trailing
    # "." blocks suffix stripping and tanks trigram recall (SEC titles almost all end this way).
    upper = re.sub(r"[.,]", " ", upper)
    upper = re.sub(r"\s+", " ", upper).strip()
    for suffix in _SUFFIXES:
        if upper.endswith(suffix):
            upper = upper[: -len(suffix)].strip()
            break
    return upper


def triage(
    similarity: float,
    mention: str,
    high_threshold: float = _HIGH,
    medium_threshold: float = _MEDIUM,
    low_threshold: float = _LOW,
) -> ResolutionStatus:
    if similarity >= high_threshold:
        return ResolutionStatus.AUTO_LINK
    if similarity >= medium_threshold:
        return ResolutionStatus.LLM_DISAMBIGUATE
    if similarity >= low_threshold:
        return ResolutionStatus.LLM_EXPAND_CONTEXT
    return ResolutionStatus.AUTO_DISMISS


def score_candidate(mention_normalized: str, candidate_normalized: str) -> float:
    """Trigram-style similarity without external dependencies.

    Uses character bigram Jaccard similarity as a pure-Python fallback.
    The production resolver uses pgvector cosine similarity from the DB;
    this function is used for unit tests and local scoring only.
    """
    if mention_normalized == candidate_normalized:
        return 1.0
    if not mention_normalized or not candidate_normalized:
        return 0.0

    def bigrams(s: str) -> set[str]:
        return {s[i : i + 2] for i in range(len(s) - 1)}

    m = bigrams(mention_normalized)
    c = bigrams(candidate_normalized)
    if not m or not c:
        return 0.0
    intersection = len(m & c)
    union = len(m | c)
    return intersection / union if union else 0.0
