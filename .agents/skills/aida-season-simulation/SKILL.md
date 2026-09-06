---
name: aida-season-simulation
description: Orchestrate the existing AIda backend season-simulation controller for a gated sample and fresh sequential season, including frozen inputs, bounded execution, safe resume, exports, and verification. Use for season campaigns, not manual weekly writing or isolated article assessment.
---

# AIda season simulation

Run the existing backend controller against a new explicitly identified disposable
target with empty canonical memory. Never delete or reset an existing database,
campaign, failed attempt or frozen artifact to obtain a clean start.

1. Read [campaign operations](../../../docs/reporter-quality/campaign-operations.md)
   for current-state discovery, preparation, exact commands and recovery rules.
   Keep one owner coordinating paid execution; reuse existing scoped authorization.
2. Freeze code, dependencies, configuration, requests, raw observations, snapshots
   and editorial cutoffs. Initialize and dry-run before any provider execution.
3. Apply the [evaluation procedure](../../../docs/reporter-quality/evaluation-procedure.md)
   to the sample. The established comparison used chronological weeks 1, 2 and 15;
   label the gaps. After the gate passes, start a separate empty-memory full-season
   target. Historical full coverage was weeks 1–17; honor requested alternatives
   and actual league coverage.
4. Run sequentially in bounded steps, inspect committed progress and exports,
   and prepare the derived semantic index between successful generations when
   enabled. Every next step consumes the preceding committed memory head.
5. Resume through controller reconciliation. Inspect running or uncertain work
   before recovery; a polling timeout never authorizes a duplicate paid job.
   Preserve failures and verify retained exports before reporting completion.

Use `aida-reporter-evaluation` for selected-week comparisons or detailed reporting
assessment. Do not rotate tone, force storyline counts or launch one writer agent
per week in place of backend generations.
