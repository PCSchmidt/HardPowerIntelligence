# Eval Baseline — Hard Power Intelligence

Citation-faithfulness baseline for the brief eval gate. Gate 5 artifact.

Gate 5 (`brief_verified`) passes when:
1. `engine/eval/citation_eval.py` is implemented and the harness runs end-to-end
2. At least one Defense brief passes `BRIEF_FAITHFULNESS_THRESHOLD` (0.95)
3. This document is populated with results from that run

---

## Configuration

| Parameter | Value | Env var |
|-----------|-------|---------|
| Faithfulness threshold | 0.95 | `BRIEF_FAITHFULNESS_THRESHOLD` |
| Eval model | Qwen3.7 Max | `LLM_MODEL_EVAL` |
| Eval call structure | Per-item (D029) | — |
| Item failure handling | Item-level exclusion (D029) | — |
| Fallback on eval failure | Previous brief + staleness indicator (D013) | — |

---

## What faithfulness_score measures

```
faithfulness_score = passing_claim_checks / total_claim_checks
```

- **All claims:** Qwen3.7 Max entailment check — "does this source passage support this claim?" → pass/fail per claim. Numeric and prose claims handled uniformly (D038).
- **Uncited claims:** any sentence in brief body without a `[CITE:N]` marker → automatic fail
- **Item-level exclusion:** if all claims in a brief item fail, the item is excluded from the published brief; remaining items' scores determine the brief-level score

---

## Baseline run results

*Populated after the first production brief generation run. Update this table after each gate evaluation.*

| Brief date | Desk | Items generated | Items excluded | Claims checked | Claims passing | Score | Published? | Notes |
|------------|------|----------------|----------------|----------------|----------------|-------|------------|-------|
| 2026-06-06 | defense | 3 | 1 | 2 | 2 | 1.000 | Yes | First integration run; 3 fixture records, 2 passages retrieved, 1 item excluded (Qwen judged LRASM claim unsupported by available passage), 2 surviving items both scored 1.00 |

---

## Score distribution

*Populated after N ≥ 5 briefs.*

| Metric | Value |
|--------|-------|
| Minimum score | — |
| Median score | — |
| Mean score | — |
| Maximum score | — |
| % briefs published (score ≥ 0.95) | — |
| % briefs falling back to D013 | — |

---

## Failure mode analysis

*Populated after first failures are observed. Document recurring failure patterns here to guide pipeline improvements.*

| Failure type | Frequency | Root cause | Resolution |
|-------------|-----------|-----------|------------|
| Uncited claim | — | — | — |
| Numeric mismatch | — | — | — |
| Entailment fail (prose) | — | — | — |

---

## Model version log

Record model changes here so score drift can be attributed to model changes vs. pipeline changes.

| Date | Role | Previous model | New model | Reason | Score impact |
|------|------|---------------|-----------|--------|-------------|
| 2026-06-05 | eval | — | qwen/qwen3.7-max | Initial selection (D006) | baseline |

---

## Threshold revision history

| Date | Previous threshold | New threshold | Reason |
|------|--------------------|---------------|--------|
| 2026-06-05 | — | 0.95 | Initial selection (D016) |
