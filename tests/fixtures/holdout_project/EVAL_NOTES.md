# Holdout Eval — What It Proves and What It Doesn't

This holdout is **synthetic** (written by the build-time model, not taken from
a real engagement). The limits below are known gaps, not footnotes — read them
before treating a passing eval as evidence of production readiness.

## Known limits of this synthetic holdout

1. **It is cleaner than real inputs.** The scope document is coherent,
   consistently structured, and free of contradictions, tracked-changes
   remnants, pricing tables, and stakeholder politics. Real scope documents
   are messier in ways that specifically stress `needs_clarification`
   behavior. A pass here does NOT demonstrate robustness to real client
   documents.
2. **The ambiguities are planted and legible.** The unknown ERP and the
   unresolved offline-conflict policy are flagged *in the text itself* ("was
   never resolved", "not recorded in the CRM"). Real ambiguity is usually
   silent — the document simply doesn't mention the thing. This eval measures
   whether the model flags *signposted* gaps, which is the easier half of the
   problem.
3. **The transcript is short, single-meeting, and well-spoken.** Real
   transcripts are longer, have ASR errors, crosstalk, and people referred to
   inconsistently ("Rob" / "Robert" / "R."). Name-to-roster matching is only
   lightly exercised.
4. **Keyword-based scoring is approximate.** The labels match by keyword, so
   a semantically-correct extraction phrased unusually can score as a miss,
   and a wrong extraction containing the right keyword can score as a hit.
   Eyeball the printed output alongside the scores.
5. **Same-author risk.** The fixture and the prompts were written by the same
   model family, which plausibly inflates scores relative to third-party
   data. Directionally useful; not an unbiased benchmark.
6. **One sample.** One scope document and one transcript — no variance
   estimate. Treat scores as smoke-test signal, not a measured capability.

## What would close these gaps

A real (anonymized) scope document and one or two real meeting transcripts
from the pilot client, labeled by a human, swapped into this directory with
the same file names. The eval scripts need no changes.

## Observed run-to-run variance (tracked characteristic)

Consecutive eval runs on identical input produced 7 phases, then 5-6 — LLM
decomposition granularity varies between runs even when every run is
individually coherent. This is a characteristic to design around (labels use
ranges, reviewers see the plan before it binds), not a defect to fix; it is
recorded here so it stays visible now that PHASE_COUNT_RANGE covers it.

## Held-out discipline

The prompts in /prompts were frozen before this fixture was first evaluated.
If anyone iterates on prompts against this fixture's output, it stops being a
holdout — note that in any reported score and create fresh holdout data.
