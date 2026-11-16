export const meta = {
  name: 'ncrecon-deploy-plan',
  description: 'Judge panel: three independent deployment-plan drafts for NC Recon, scored, synthesised, adversarially reviewed and revised',
  phases: [
    { title: 'Draft', detail: 'three plans from different angles, grounded in the verified research' },
    { title: 'Judge', detail: 'three judges score every draft and name what the synthesis must keep' },
    { title: 'Synthesise', detail: 'one plan from the winner plus grafted ideas' },
    { title: 'Review', detail: 'two adversarial reviewers, then one revision' },
  ],
}

const { today, current_state_path, record_path, record_md_path } = args

const COPY_RULES = `Writing rules (the project's DESIGN.md): no em dashes anywhere (use commas, colons or full stops); sentence case for headings; real source, programme and product names; never invent a number, date, price or statistic, and when you cite one say where it comes from (the research record or the current-state text); FEMA's five damage levels are No damage, Affected, Minor, Major, Destroyed; plain, specific prose; mark anything unverified as such.`

const BRIEF = `Today is ${today}. NC Recon is an open-source damage decision-support tool for North Carolina emergency management. The user asked for: a full plan for the program to be ready to deploy for real NC emergency offices, covering functionality in real disasters (pre, during and post), data sources including live tracking and monitoring, drone imagery and 3D modelling, UI design, security, deployment and procurement.

Before writing anything, read these two files with the Read tool (they are the evidence base; the plan must be grounded in them and must not invent beyond them):
1. ${current_state_path}  (what NC Recon is and does today, written from the code)
2. ${record_md_path}  (the research record: 12 dimensions, every source with access, licence, NC coverage, cadence, caveats; high-priority sources carry an independent verifier's verdict and corrections, which override the original claim; each dimension ends with insights and gaps; the file ends with a completeness critic). The same record as JSON is at ${record_path} if you prefer to parse it.
Read the whole record, not a part of it: it is long, so read it in several Read calls with offsets.
`

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    title: { type: 'string' },
    thesis: { type: 'string', description: 'the one-paragraph argument of this plan' },
    sections: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          heading: { type: 'string' },
          body_markdown: { type: 'string', description: 'full prose and tables for this section, markdown, grounded in the record' },
        },
        required: ['heading', 'body_markdown'],
      },
    },
    integrations_ranked: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          source: { type: 'string' },
          phase: { type: 'string' },
          why_now: { type: 'string' },
          effort: { type: 'string', enum: ['days', 'weeks', 'months'] },
          blocker: { type: 'string' },
        },
        required: ['source', 'phase', 'why_now', 'effort'],
      },
    },
    milestones: { type: 'array', items: { type: 'object', properties: { name: { type: 'string' }, exit_criteria: { type: 'string' }, depends_on: { type: 'string' } }, required: ['name', 'exit_criteria'] } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['title', 'thesis', 'sections', 'integrations_ranked', 'milestones', 'open_questions'],
}

const ANGLES = [
  { key: 'user-first', prompt: `Write the plan from the point of view of the people who will use it: a county emergency management director in western North Carolina, the GIS analyst in the state EOC planning section, a field damage-assessment team lead, and a PIO who has to publish numbers. Organise it around what each needs in the 72 hours before landfall, the first 48 hours, days 2 to 10 when imagery arrives, and the weeks after. Be specific about screens, workflows, exports, and the hand-offs to WebEOC, ArcGIS, FEMA PDA and recovery case management. Cover UI design in depth (EOC wall display, analyst desktop, field phone, print), accessibility, Spanish, offline. Still cover data, security and procurement, but through what they enable for those users.` },
  { key: 'risk-first', prompt: `Write the plan from the point of view of the state CIO's security office, the NCEM lawyer and the FEMA PDA lead. Lead with everything that could stop adoption or cause harm: unvalidated accuracy and how to validate (labels, calibration, holdouts, per-event accuracy reporting), licensing of inputs (Maxar CC BY-NC, ODbL, xView2 weights), public records and privacy of address-level damage, identity and access (NCID or Entra ID SSO, MFA, roles, break-glass), audit, data classification, StateRAMP/NIST expectations, Section 508, incident response, backups and continuity during an outage, supply chain, and what evidence FEMA accepts in a PDA so the tool's outputs are usable rather than ignored. Then the functionality and data plan that survives those constraints, pre, during and post.` },
  { key: 'engineering-first', prompt: `Write the plan as the engineering lead who has to ship it with a small team and no paid services: architecture changes (identity provider, multi-user roles, job workers, storage, offline packs, tile serving, self-hosted basemap, GPU or CPU), the ranked list of data integrations with exact endpoints and licences from the record (live feeds, drone imagery ingest through OpenDroneMap-style orthomosaics, lidar and 3D, satellite SAR/optical, infrastructure status, ground truth), new evidence channels and how each is validated before it changes a call, pre-event baselines and triggers, during-event monitoring, post-event recovery tracking, test strategy, CI/CD, release and patch cadence, observability, cost of hosting (state cloud vs on-prem vs GovCloud) with any figures only from the record, and a phased roadmap with exit criteria.` },
]

phase('Draft')
const drafts = await parallel(ANGLES.map(a => () =>
  agent(`${BRIEF}\n\n${COPY_RULES}\n\nYOUR ANGLE: ${a.prompt}\n\nProduce a complete plan (aim for the depth of a 6,000 to 9,000 word document across the sections) with these sections at minimum: Executive summary; What exists and what is missing; Pre-disaster readiness; During the event; Post-event damage assessment and recovery; Data and live feeds (ranked integrations with access and licence); Drone imagery and 3D; Evidence and validation; UI design; Security, privacy and legal; Deployment, hosting and operations; Procurement, funding and partners; Roadmap with milestones and exit criteria; Risks; Open questions for NCEM. Ground every claim in the record; where the record is silent, say so rather than invent.`,
    { label: `draft:${a.key}`, phase: 'Draft', schema: PLAN_SCHEMA })
    .then(p => p && ({ ...p, key: a.key }))))
const good = drafts.filter(Boolean)
log(`Drafts: ${good.length}/3`)

phase('Judge')
const SCORE = {
  type: 'object',
  properties: {
    scores: { type: 'array', items: { type: 'object', properties: { draft: { type: 'string' }, fit_to_nc_practice: { type: 'number' }, grounding: { type: 'number' }, completeness_pre_during_post: { type: 'number' }, feasibility_small_team_no_paid: { type: 'number' }, security_legal: { type: 'number' }, specificity: { type: 'number' }, total: { type: 'number' }, rationale: { type: 'string' } }, required: ['draft', 'total', 'rationale'] } },
    winner: { type: 'string' },
    must_keep_from_each: { type: 'array', items: { type: 'object', properties: { draft: { type: 'string' }, ideas: { type: 'array', items: { type: 'string' } } }, required: ['draft', 'ideas'] } },
    errors_to_drop: { type: 'array', items: { type: 'string' }, description: 'claims in any draft that contradict the record, invent figures, or break the copy rules; name the draft' },
  },
  required: ['scores', 'winner', 'must_keep_from_each', 'errors_to_drop'],
}
const draftsText = good.map(d => `=== DRAFT ${d.key}: ${d.title}\nTHESIS: ${d.thesis}\n` + d.sections.map(s => `## ${s.heading}\n${s.body_markdown}`).join('\n') + `\nINTEGRATIONS: ${JSON.stringify(d.integrations_ranked)}\nMILESTONES: ${JSON.stringify(d.milestones)}\nOPEN QUESTIONS: ${JSON.stringify(d.open_questions)}`).join('\n\n')
const JUDGES = ['a county EM director who has run a real EOC through a federally declared flood', 'a state GIS and IT security lead who approves tools for an EOC network', 'a disaster-remote-sensing scientist who has evaluated damage models against ground truth']
const judgements = (await parallel(JUDGES.map((who, i) => () =>
  agent(`${BRIEF}\n\nYou are ${who}. Score each draft from 1 to 10 on: fit to NC EM practice, grounding in the record (penalise invented or unsupported claims heavily), completeness across pre, during and post, feasibility for a small team with no paid services, security and legal soundness, specificity (names, endpoints, exit criteria). Give a total and rationale per draft, pick a winner, list the ideas from each draft that the final synthesis must keep, and list errors to drop.\n\n${draftsText}`,
    { label: `judge:${i}`, phase: 'Judge', schema: SCORE })))).filter(Boolean)
const tally = {}
judgements.forEach(j => j.scores.forEach(s => { tally[s.draft] = (tally[s.draft] || 0) + (s.total || 0) }))
const winner = Object.keys(tally).sort((a, b) => tally[b] - tally[a])[0]
log(`Judges: totals ${JSON.stringify(tally)}, winner ${winner}`)

phase('Synthesise')
const synthesis = await agent(`${BRIEF}\n\n${COPY_RULES}\n\nYou are the editor. The judges scored three drafts; the winner is "${winner}" (totals ${JSON.stringify(tally)}). Their verdicts:\n${JSON.stringify(judgements, null, 1)}\n\nWrite the final plan as one markdown document, starting from the winning draft's structure and grafting every "must keep" idea from the other drafts, dropping every listed error. Keep the depth (6,000 to 9,000 words). Use these top-level sections in this order: Executive summary; Where NC Recon stands; How NC emergency management works and where the tool fits; Pre-disaster readiness; During the event; Post-event assessment and recovery; Data sources and live feeds (one ranked table: source, operator, access, licence, NC coverage, phase, what it feeds, priority, verified?); Drone imagery and 3D; Evidence channels and validation; UI design; Security, privacy and legal; Deployment, hosting and operations; Procurement, funding and partners; Roadmap (milestones with exit criteria); Risks; Open questions for NCEM; Sources (every URL cited). Every figure must trace to the record or the current-state text. Output only the markdown.\n\n${draftsText}`,
  { label: 'synthesis', phase: 'Synthesise' })

phase('Review')
const REVIEW = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: { section: { type: 'string' }, problem: { type: 'string' }, fix: { type: 'string' }, severity: { type: 'string', enum: ['high', 'medium', 'low'] } }, required: ['section', 'problem', 'fix', 'severity'] } },
  },
  required: ['findings'],
}
const reviews = (await parallel([
  `You are a fact checker. Compare every claim, name, endpoint, licence, date and figure in the plan with the research record and the current-state text. Flag anything unsupported, contradicted, refuted or doubtful in the verification verdicts, any invented number, any dead or decommissioned service presented as live, and any licence misstatement. Give the exact fix.`,
  `You are an NC emergency-management practitioner and a copy editor. Flag: anything that does not fit how NCEM, counties and FEMA actually work; missing pre, during or post functionality a real EOC would ask for; vague milestones without exit criteria; em dashes, title-case headings, invented statistics, marketing language, hedging that hides a decision. Give the exact fix.`,
].map((who, i) => () =>
  agent(`${BRIEF}\n\n${COPY_RULES}\n\n${who}\n\nTHE PLAN:\n${synthesis}`, { label: `review:${i}`, phase: 'Review', schema: REVIEW })))).filter(Boolean)
const findings = reviews.flatMap(r => r.findings)
log(`Review: ${findings.length} findings (${findings.filter(f => f.severity === 'high').length} high)`)

const revised = await agent(`${COPY_RULES}\n\nApply every finding below to the plan and output the complete revised markdown document (and nothing else). Do not shorten the plan; fix, correct, add. Where a finding asks for information the record does not contain, write that it is unknown and list it under Open questions rather than inventing it.\n\nFINDINGS:\n${JSON.stringify(findings, null, 1)}\n\nRESEARCH RECORD AND CURRENT STATE (for corrections):\n${BRIEF}\n\nTHE PLAN:\n${synthesis}`,
  { label: 'revise', phase: 'Review' })

return { winner, tally, judgements, findings, drafts: good.map(d => ({ key: d.key, title: d.title, thesis: d.thesis })), plan: revised }
