"""Reference entity set from SEC company_tickers.json (T3.1, D091).

The SEC publishes a free, authoritative ticker↔CIK↔name map for every filer. We seed it as the
resolver's target set: one ``entities`` row per public company, with ``entity_identifiers``
(ticker, cik) and an ``entity_aliases`` row (the normalized title for matching). Private /
venture entities without a ticker are minted later from our own authoritative ingest
identifiers (UEI/CIK) — see D091. This module is pure parsing/shaping; the DB upsert lives in
``scripts/seed_entities.py`` (operator-run).
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.entity.resolver import normalize_mention

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


@dataclass(frozen=True)
class CompanyRef:
    """One public company from the SEC map, shaped for seeding."""
    cik: str             # zero-padded 10-digit CIK (SEC canonical form)
    ticker: str          # upper-cased exchange ticker
    name: str            # canonical_name (the SEC "title")
    name_normalized: str  # normalize_mention(name) — the alias used for matching


def pad_cik(cik: object) -> str:
    """SEC CIKs are canonical as zero-padded 10-digit strings (e.g. 320193 -> 0000320193)."""
    return str(cik).strip().zfill(10)


def parse_company_tickers(payload: dict) -> list[CompanyRef]:
    """Parse the SEC company_tickers.json object into de-duped CompanyRefs.

    The file is a JSON object keyed by row index: ``{"0": {"cik_str": 320193, "ticker":
    "AAPL", "title": "Apple Inc."}, ...}``. Rows missing a ticker or title are skipped (we
    can't resolve to or label a company without both). De-duped on (ticker, cik) so a repeated
    listing doesn't create duplicate identifiers.
    """
    out: list[CompanyRef] = []
    seen: set[tuple[str, str]] = set()
    for row in (payload or {}).values():
        if not isinstance(row, dict):
            continue
        ticker = (row.get("ticker") or "").strip().upper()
        title = (row.get("title") or "").strip()
        cik_raw = row.get("cik_str")
        if not ticker or not title or cik_raw is None:
            continue
        cik = pad_cik(cik_raw)
        key = (ticker, cik)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            CompanyRef(
                cik=cik,
                ticker=ticker,
                name=title,
                name_normalized=normalize_mention(title),
            )
        )
    return out
