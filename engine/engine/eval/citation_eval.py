import re
from dataclasses import dataclass

import structlog

from engine.brief.rag import PassageContext
from engine.llm.client import llm_client, parse_json
from engine.settings import settings

log = structlog.get_logger()

_CITE_RE = re.compile(r"\[CITE:(\d+)\]")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


@dataclass
class Claim:
    id: str
    text: str
    citation_indices: list[int]

    @property
    def is_cited(self) -> bool:
        return bool(self.citation_indices)


@dataclass
class EvalResult:
    item_id: str
    excluded: bool
    claims_total: int
    claims_passing: int
    faithfulness_score: float
    cleaned_body: str = ""   # body with only LLM-supported, cited sentences (D069)


def extract_citation_indices(text: str) -> list[int]:
    return list(dict.fromkeys(int(m) for m in _CITE_RE.findall(text)))


def strip_uncited_sentences(body: str) -> str:
    """Remove sentences that lack a ``[CITE:N]`` citation (D058).

    A sentence with no citation is, by the brief's own invariant, unsupported —
    so rather than fail the whole item on one stray sentence, we drop the
    offending sentence and publish only what's provable. Returns the cleaned
    body (possibly empty if nothing was cited)."""
    if not body:
        return ""
    sentences = _SENTENCE_RE.split(body.strip())
    kept = [s.strip() for s in sentences if s.strip() and _CITE_RE.search(s)]
    return " ".join(kept)


def extract_claims(body: str) -> list[Claim]:
    if not body:
        return []
    sentences = _SENTENCE_RE.split(body.strip())
    claims = []
    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue
        claims.append(Claim(
            id=f"c{i}",
            text=sentence,
            citation_indices=extract_citation_indices(sentence),
        ))
    return claims


class CitationEvaluator:
    def __init__(self, eval_model: str | None = None):
        self.eval_model = eval_model or settings.llm_model_eval

    async def eval_item(
        self,
        item_id: str,
        body: str,
        passages: list[PassageContext],
    ) -> EvalResult:
        claims = extract_claims(body)
        if not claims:
            return EvalResult(
                item_id=item_id, excluded=True,
                claims_total=0, claims_passing=0, faithfulness_score=0.0,
            )

        # Uncited claims auto-fail — separate them before the LLM call
        uncited = [c for c in claims if not c.is_cited]
        cited = [c for c in claims if c.is_cited]

        # Build passage lookup for this item's cited indices
        cited_indices = {idx for c in cited for idx in c.citation_indices}
        relevant_passages = [p for p in passages if p.index in cited_indices]

        passing = 0
        cleaned_body = ""

        if cited:
            sources_block = "\n".join(
                f"[{p.index}] {p.excerpt}" for p in relevant_passages
            ) or "No sources provided."

            claims_block = "\n".join(
                f"id={c.id}: {c.text}" for c in cited
            )

            user_content = (
                f"SOURCE PASSAGES:\n{sources_block}\n\n"
                f"CLAIMS TO EVALUATE:\n{claims_block}\n\n"
                "For each claim, check whether the cited [CITE:N] source passage directly supports "
                "the factual assertion in the claim. Return only this JSON:\n"
                '{"claim_evaluations": [{"id": "c0", "supported": true}, ...]}'
            )
            messages = [
                {
                    "role": "system",
                    "content": "You are a citation-faithfulness evaluator. A claim is supported if the cited source passage directly contains the stated fact. Return only valid JSON.",
                },
                {"role": "user", "content": user_content},
            ]
            content = await llm_client.complete(
                model=self.eval_model,
                messages=messages,
                json_mode=True,
                temperature=settings.llm_temperature,
            )
            parsed = parse_json(content) or {}
            evaluations = {
                e["id"]: e.get("supported", False)
                for e in parsed.get("claim_evaluations", [])
            }
            passing = sum(1 for c in cited if evaluations.get(c.id, False))
            # Publish only the individually-supported sentences (D069): a partially
            # over-claimed item is trimmed to its provable sentences rather than
            # dragging the whole brief below threshold. Sentence order preserved.
            cleaned_body = " ".join(
                c.text for c in cited if evaluations.get(c.id, False)
            )

        total = len(claims)
        # Excluded iff nothing provable survived (equivalent to the old passing==0).
        excluded = not cleaned_body

        if total == 0:
            score = 0.0
        else:
            score = passing / total  # uncited claims count as failing in denominator

        log.info(
            "item_eval",
            item_id=item_id,
            total=total,
            passing=passing,
            uncited=len(uncited),
            excluded=excluded,
        )

        return EvalResult(
            item_id=item_id,
            excluded=excluded,
            claims_total=total,
            claims_passing=passing,
            faithfulness_score=score,
            cleaned_body=cleaned_body,
        )

    def brief_faithfulness_score(self, results: list[EvalResult]) -> float:
        surviving = [r for r in results if not r.excluded]
        if not surviving:
            return 0.0
        total = sum(r.claims_total for r in surviving)
        passing = sum(r.claims_passing for r in surviving)
        return passing / total if total else 0.0

    def provable_claim_count(self, results: list[EvalResult]) -> int:
        """Total individually-supported claims across surviving items (D070).

        The publish gate counts provable *claims*, not items, because the synthesis
        non-deterministically packs the same facts into few dense items or many thin
        ones — claim count is stable to that, item count is not."""
        return sum(r.claims_passing for r in results if not r.excluded)
