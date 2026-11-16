# Deployment-readiness research (2026-10-06/07)

What is here:

* `deployment-research-record-2026-10-07.md` (and `.json`): the condensed output of a
  12-dimension web research sweep (452 sources, 203 marked high priority) on what
  NC Recon needs to be deployable for real NC emergency offices: satellite and
  aerial/drone imagery, lidar and 3D, live hazard and lifeline feeds, ground truth,
  how NCEM and counties operate and buy software, security and legal, UI/UX for
  EOCs, the state of the art in damage models, pre-disaster readiness and
  post-disaster recovery. Each source carries access, auth, licence, NC coverage,
  cadence, caveats and how NC Recon would use it; each dimension ends with
  insights and the gaps the researcher could not close. Only a handful of
  high-priority sources were independently re-verified before the session ended
  (`verdict` fields); treat the rest as researched, not verified.
* `current-state-2026-10-07.md`: where the code stood that day, written for the plan.
* `research-workflow.js`, `build-record.py`, `plan-workflow.js`: the orchestration
  scripts (the research sweep; the condenser; the unrun plan-drafting panel that
  reads the two files above).

What was built from the record the same day: request guard (rate limits, CSP),
bundled fonts, CI audits and SBOMs, three Conditions feeds (NC FIMAN gauges, Duke
Energy outages, FEMA shelters) and the first flood-depth water-surface source
(NCEM `Peak_Stage_Helene`); see `docs/ops/PHASE_J_STATUS.md`.

The full deployment plan has not been written yet; `DEPLOYMENT_PLAN_OUTLINE.md`
holds the outline and the findings it will rest on.
