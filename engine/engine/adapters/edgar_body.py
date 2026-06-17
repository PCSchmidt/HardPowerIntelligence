"""EDGAR filing-body extraction (D078).

The EFTS metadata adapter (D060) gives company/form/date/theme but no numbers — the
publish gate counts *provable claims*, and a bare "Acme filed an 8-K" sentence has no
checkable fact in it. This module pulls the actual filing document and mines it for the
fact-dense specifics the gate rewards: dollar amounts, percentages, and dates. No new
dependency — HTML is stripped with the stdlib ``html.parser`` (SEC primary docs are HTML
or plain text), and facts are pulled with regex (the robust, local-side complement to
EFTS's phrase-only query, per the operator's "wildcards" instinct).

The biggest single win is ``amount_usd``: the materiality scorer (D035) magnitude-
normalizes ``structured_data['amount_usd']``, which EFTS metadata never carried — so a
body-extracted award/contract figure now actually feeds materiality, not just synthesis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Multipliers for "$1.5 billion" / "$3.2B" style figures → USD.
_SCALE = {
    "trillion": 1_000_000_000_000, "tn": 1_000_000_000_000, "t": 1_000_000_000_000,
    "billion": 1_000_000_000, "bn": 1_000_000_000, "b": 1_000_000_000,
    "million": 1_000_000, "mn": 1_000_000, "mm": 1_000_000, "m": 1_000_000,
    "thousand": 1_000, "k": 1_000,
}

# "$1.5 billion", "$1,200 million", "$500,000", "$3.2B" — number then optional scale word.
_AMOUNT_RE = re.compile(
    r"\$\s*([\d][\d,]*(?:\.\d+)?)\s*"
    r"(trillion|billion|million|thousand|tn|bn|mm|mn|[bmkt])?\b",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s?%")
# "May 7, 2026" / "May 7 2026"
_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},?\s+\d{4}\b"
)
_WS_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    """Collect visible text, dropping <script>/<style> content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self._parts.append(data)

    def text(self) -> str:
        return _WS_RE.sub(" ", " ".join(self._parts)).strip()


def strip_html(raw: str) -> str:
    """Return visible plain text from an HTML (or already-plain) filing body."""
    if not raw:
        return ""
    if "<" not in raw:  # already plain text (some filings are .txt)
        return _WS_RE.sub(" ", raw).strip()
    parser = _TextExtractor()
    try:
        parser.feed(raw)
    except Exception:  # noqa: BLE001 — malformed HTML: keep whatever was parsed
        pass
    return parser.text()


def _parse_amount(number: str, scale: str | None) -> float | None:
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    if scale:
        value *= _SCALE.get(scale.lower(), 1)
    return value


@dataclass
class FilingFacts:
    amounts_usd: list[float] = field(default_factory=list)
    percentages: list[float] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)

    @property
    def max_amount_usd(self) -> float | None:
        return max(self.amounts_usd) if self.amounts_usd else None

    def summary(self) -> str:
        """A compact, citable facts line to fold into the embedded text_chunk."""
        bits: list[str] = []
        if self.amounts_usd:
            top = sorted(set(self.amounts_usd), reverse=True)[:3]
            bits.append("amounts " + ", ".join(_fmt_usd(a) for a in top))
        if self.percentages:
            top = sorted(set(self.percentages), reverse=True)[:3]
            bits.append("rates " + ", ".join(f"{p:g}%" for p in top))
        if self.dates:
            seen = list(dict.fromkeys(self.dates))[:3]
            bits.append("dates " + "; ".join(seen))
        return "Key figures: " + " | ".join(bits) + "." if bits else ""


def _fmt_usd(value: float) -> str:
    for unit, label in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if value >= unit:
            return f"${value / unit:g}{label}"
    return f"${value:g}"


def extract_facts(text: str, *, max_each: int = 25) -> FilingFacts:
    """Pull dollar amounts (→ USD), percentages, and dates from filing text."""
    amounts: list[float] = []
    for number, scale in _AMOUNT_RE.findall(text)[:max_each]:
        amt = _parse_amount(number, scale or None)
        if amt is not None:
            amounts.append(amt)
    percentages = [float(m) for m in _PERCENT_RE.findall(text)[:max_each]]
    dates = [m.group(0) for m in list(_DATE_RE.finditer(text))[:max_each]]
    return FilingFacts(amounts_usd=amounts, percentages=percentages, dates=dates)


def build_enriched_chunk(metadata_chunk: str, body_text: str, facts: FilingFacts,
                         *, excerpt_chars: int) -> str:
    """Metadata line + extracted key figures + a substantive body excerpt.

    The excerpt is centred on the first dollar amount when present (skipping cover-page
    boilerplate); otherwise it skips a fixed boilerplate prefix. This is what gets
    embedded, so RAG retrieves passages that actually contain the numbers the citation
    eval needs to verify a claim."""
    summary = facts.summary()
    excerpt = _meaningful_excerpt(body_text, excerpt_chars)
    return " ".join(p for p in (metadata_chunk, summary, excerpt) if p).strip()


def _meaningful_excerpt(body_text: str, excerpt_chars: int) -> str:
    if not body_text or excerpt_chars <= 0:
        return ""
    m = _AMOUNT_RE.search(body_text)
    if m:
        start = max(0, m.start() - excerpt_chars // 3)
    else:
        start = min(len(body_text), 400)  # skip typical cover-page boilerplate
    return body_text[start:start + excerpt_chars].strip()


# ── Form D (Reg D private placement) extraction (D081) ───────────────────────────
# Form D's primary document is structured XML (primary_doc.xml), not prose — the
# offering figures live in named tags, so they parse cleanly with targeted regex.
_FORMD_OFFERING_RE = re.compile(
    r"<totalOfferingAmount>\s*([\d,.]+)\s*</totalOfferingAmount>", re.IGNORECASE
)
_FORMD_SOLD_RE = re.compile(
    r"<totalAmountSold>\s*([\d,.]+)\s*</totalAmountSold>", re.IGNORECASE
)
_FORMD_INDUSTRY_RE = re.compile(
    r"<industryGroupType>\s*([^<]+?)\s*</industryGroupType>", re.IGNORECASE
)


def _to_float(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None  # Form D allows "Indefinite" for the offering amount


@dataclass
class FormDFacts:
    total_offering_usd: float | None = None
    total_sold_usd: float | None = None
    industry: str | None = None

    @property
    def amount_usd(self) -> float | None:
        """The figure to feed materiality: the raise size, else what's sold so far."""
        return self.total_offering_usd or self.total_sold_usd

    def summary(self) -> str:
        bits: list[str] = []
        if self.total_offering_usd is not None:
            bits.append(f"offering {_fmt_usd(self.total_offering_usd)}")
        if self.total_sold_usd is not None:
            bits.append(f"{_fmt_usd(self.total_sold_usd)} sold to date")
        if self.industry:
            bits.append(f"industry {self.industry}")
        return "; ".join(bits)


def extract_form_d_facts(xml: str) -> FormDFacts:
    """Pull the offering size, amount sold, and industry from a Form D primary_doc.xml."""
    if not xml:
        return FormDFacts()
    off = _FORMD_OFFERING_RE.search(xml)
    sold = _FORMD_SOLD_RE.search(xml)
    ind = _FORMD_INDUSTRY_RE.search(xml)
    return FormDFacts(
        total_offering_usd=_to_float(off.group(1) if off else None),
        total_sold_usd=_to_float(sold.group(1) if sold else None),
        industry=ind.group(1).strip() if ind else None,
    )


def build_form_d_chunk(company: str, ticker: str | None, facts: FormDFacts) -> str:
    """A citable one-line text_chunk for a Form D private placement (D081)."""
    tick = f" ({ticker})" if ticker else ""
    detail = facts.summary() or "amount not disclosed"
    return f"SEC Form D private placement by {company}{tick}: {detail}."
