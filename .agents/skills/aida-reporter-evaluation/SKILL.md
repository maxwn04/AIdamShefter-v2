---
name: aida-reporter-evaluation
description: Run and assess the actual AIda backend reporter for selected weeks or matched comparisons, reviewing generated articles, executed sources, retrieval, and committed memory. Use for reporter quality evaluation, not manual article writing or full-season orchestration.
---

# AIda reporter evaluation

Evaluate product-generated reporting. Use the backend generation service through
the existing season controller for reproducible selected-week runs; never write
a substitute article or manually apply memory to make a run appear successful.

1. Read [evaluation procedure](../../../docs/reporter-quality/evaluation-procedure.md).
   Establish the current checkout/PR implementation and latest accepted evidence;
   an old plan, a generated article, and a passing test are different kinds of evidence.
2. For new generations, use the shared
   [campaign operations](../../../docs/reporter-quality/campaign-operations.md)
   to freeze the request, source inputs, settings and memory starting point.
   Paid reporter and embedding execution must be covered by the user's current
   authorization; retain authorization already granted within that scope.
3. Inspect the submitted article alongside executed source results, traces and
   actual before/after canonical memory. Assess factual and editorial quality,
   discovery relevance, storyline identity and callback outcomes separately.
4. Report evidence-backed improvements, regressions, omissions and failures,
   with a clear acceptance decision and limits. Quality takes priority over
   tokens, bytes, latency and cost.

For a sequential season, use `aida-season-simulation` to own orchestration and
this procedure for its sample gate and article/memory reviews. An offline review
of retained exports needs no generation, target reset or provider call.
