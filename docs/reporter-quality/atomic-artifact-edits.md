# Atomic independent artifact edits

The reporter sometimes knows several independent corrections but serializes
separate replacements across artifact revisions. The existing tool can replace a
whole passage or article; this candidate avoids requiring that larger rewrite. This candidate adds an optional `edits` list
to the existing tool. Every exact match is validated against the same original
content; missing, ambiguous or overlapping matches reject the entire batch. A
successful batch creates one revision and one recorded mutation. Existing single
replacements remain supported. The current revision, finalized-artifact and
recording rollback guarantees remain enforced by the existing artifact store.

Thirty-four targeted tests cover the batch boundary and existing artifact tools,
including retries, stale revisions, ambiguous overlapping occurrences, Unicode,
no-ops, immutable submitted articles and database-recording failure. An offline
replay reproduced an unchanged accepted article using two revisions instead of
eight. That is implementation evidence, not a live efficiency result.

E33 preserved one failed infrastructure request, then completed one explicitly
authorized recovery. In the frozen one-response comparison, treatment applied five
preplanned independent edits in one revision; control applied one. Added facts
were already present in the frozen evidence. Original factual weaknesses remained,
and the accepted article was never changed. This supports narrow feasibility only.

E34 is a separately preregistered pair of complete Week 4 runs from the original
Week 3 checkpoint, changing only this tool. Both arms completed in 29 calls. Treatment used four edit calls, including two
valid four-replacement batches, versus seven in control. No new edit-induced
factual error or lost material information was found. However, greater research
and drafting work made treatment more expensive overall ($0.133525812 versus
$0.121909464). Storyline-question drift and unsupported future-pick inference
remained. This supports adoption and local editing efficiency, not better memory,
article quality or total cost. A chronological robustness follow-up is planned.
The roster-slot candidate, verifier experiments and rejected memory prompts are
not inherited. No merge or deployment is proposed by this experiment.
