# NC Recon Phase J: operational GEOINT upgrade (source brief)

The full Phase J brief (researched 2026-09-25) was provided in the working
session that started this phase. Its requirements are tracked, with what was
built, what changed and what differs from the brief, in
[`PHASE_J_STATUS.md`](PHASE_J_STATUS.md). The CAC-specific parts (student
authorship, AI-usage log, milestone dates, judge Q&A) were dropped at the
team's direction: the competition is over and the goal is a tool NC emergency
management offices can use.

Core principles carried forward:

1. Do not break the demo (`cac-v2-demo-stable` tag; ops mode is opt-in).
2. Verify every source live before trusting it; never invent data.
3. Measure before improving (honest baseline first).
4. Provenance on every layer, feature and export row.
5. Physics-based signals are rules with documented thresholds; fuzzy patterns are ML; context sets trust.
6. Uncertainty is a feature: probabilities, reason codes, abstention to human review.
7. CPU-only laptop budget; cloud-native windowed reads.
