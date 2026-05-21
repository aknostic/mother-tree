# 5 Freedom to Operate

We call this *freedom to operate* rather than *sovereignty*. The reframe is not a political move; it is a procurement question we found ourselves answering more usefully under one phrasing than the other.

## 5.1 The reframe

In the European conversation, "sovereign AI" has drifted toward a political register about jurisdiction, national capability, and refusing a foreign government's reach. We do not dispute that register. We observe only that the phrase has been co-opted by the hyperscalers whose dominance it nominally addresses, and that what is left does more rhetorical than operational work. Asking instead which choices about this system would we lose if a particular dependency were withdrawn tomorrow gives us a cleaner answer: a system has freedom to operate when the answer is "few enough to continue." By that test, Mother Tree could continue without US frontier inference, with the quality cost named in §5.3. Section 5.2 shows where the Anthropic dependencies sit today.

## 5.2 The model selection map

Mother Tree's models are configured in `jobs/mothertree/config.py`. Table 1 shows the assignment.

| Role | Model | Provider | Class |
|---|---|---|---|
| Light extraction & classification | Mistral Small 3.2 24B | Scaleway | Open weight, EU |
| Deep extraction (foundation, narrative) | Claude Opus 4.6 | Anthropic | Closed, US |
| Bot conversation, persona responses, training | Qwen 3.5 397B | Scaleway | Open weight, EU |
| Embeddings | BGE Multilingual Gemma2 | Scaleway | Open weight, EU |
| Multi-judge scoring (3×) | Devstral 2 123B / Llama 3.3 70B / Gemma 3 27B | Scaleway | Open weight, EU |
| Spotter, Triage | Claude Haiku 4.5 | Anthropic | Closed, US |
| Weaver, Arbitration, premium conversation | Claude Sonnet 4.6 | Anthropic | Closed, US |

The shape that matters is the named, replaceable Anthropic surface. **Embeddings, multi-judge scoring, training generation, and persona conversation** run on European open-weight inference on Scaleway. **Deep extraction, single-message classification (Spotter, Weaver), and judge arbitration** run on Anthropic because, as of this writing, no open-weight model we tested was reliable enough at the false-positive rates the work demands. The architectural commitment of the paper is not "no Anthropic in the runtime"; it is that every Anthropic call is named, can be substituted (we have tried), and the substrate, the schedule, and the data layer do not depend on Anthropic-specific features.

## 5.3 The cost

Open-weight models we have tested are materially inferior to frontier proprietary models for the workloads where judgement is concentrated: single-pass classification (Spotter, Weaver, triage, arbitration) and structured deep extraction. Qwen 3.5 397B in the Spotter and Weaver roles produced higher false-positive and false-negative rates on test inputs; for deep extraction it produced thinner reframes and looser schema adherence than Claude Opus 4.6. We choose quality at those points and run Qwen everywhere else, where the output is paragraphs the user reads rather than records the substrate has to live with.

### Observed properties of the stack

Our first ingestion run returned 944 foundation records on a corpus we expected to be small — hundreds of near-duplicates differing only in surface phrasing. We rewrote extraction to be context-aware (each document gets the existing records in its prompt) and reran; the new count was 303. We have been suspicious of model-only benchmarks since.

Corpus: 289 source documents (110 foundation, 179 narrative) from the Aknostic marketing repository and the Clouds of Europe sitemap.

*Context-aware extraction.* Qwen 3.5 397B with existing records injected as prompt context produced 303 foundation records on the same corpus where Mistral Small 3.2 with no context produced 944, a 68% drop in extraction-time duplicates. LLM-driven consolidation across all records (running over the Qwen output) reduced that further to 189, with the strongest effect on personas (28 → 9) and competitors (67 → 17).

*Judge behaviour on this corpus.* A Qwen narrative-extraction run with multi-judge scoring on the test corpus produced 816 scored insights; 815 cleared the quorum-accept threshold and 1 was flagged. Mean judge confidence was 0.87, median 0.88. A separate Opus extraction with cross-record consolidation on the same corpus produced 977 insights (used for downstream training), of which 2 were flagged. We report both because they came from different extraction backends; the architectural property under test (quorum-based admission, not a specific extractor) is the same in either case.

A 99.9% auto-accept rate could mean the system is well-calibrated or it could mean the judges (trained on overlapping internet data) are correlated and the thresholds lenient. Our corpus is single-voice; we expect higher disagreement on a more heterogeneous one. A reviewer-facing queue with sampling is future work (§8.3).

## 5.4 The benefit

Four concrete properties come up repeatedly in design conversations:

1. **Data residency at the substrate.** Every byte at rest, every backup, every embedding, and every interaction record lives in European infrastructure (Scaleway, Paris). The Anthropic surface is named in §5.2; whether the deep-extraction call to it counts as a residency violation is a deployment-time decision against the deploying organisation's data-classification regime, not a system-level claim.
2. **Model optionality.** Because the core relies on the OpenAI-compatible API shape, swapping inference providers requires changing one base URL and one set of model identifiers. We have, in the lifetime of the project, swapped extraction models several times without architectural change.
3. **Cost predictability.** Open-weight inference on Scaleway is priced per-token. Frontier providers use tier-based pricing and rate limits that turn forecasting into a step function above certain volumes. Because each cron tick has a known token budget, provider switches are arithmetic.
4. **No autonomous-loop lock-in.** The system does not depend on a particular agent runtime, and so does not inherit a particular runtime's view of which models support tool use, parallel function calling, or specific structured-output formats. The choreography described in §4 makes the inference layer a function, not a partner.

