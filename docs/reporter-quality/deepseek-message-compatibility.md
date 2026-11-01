# Provider reasoning and cache telemetry compatibility

During memory closeout, the runner can receive an assistant response without tool
calls and then make another completion request. The existing text-only path kept
the response text but discarded its reasoning content. The empty-text path did
not append an assistant message at all. Both paths now use the same message
construction as tool-call responses, removing only the empty tool-call array and
preserving provider fields. Empty responses without text or provider continuation
state retain the previous skip behavior. This allows a later request to retain the original
provider reasoning across all closeout turns.

Token telemetry also recognizes `prompt_cache_hit_tokens` as a fallback cached
input count. An explicitly reported zero in the standard nested field still
wins. Reasoning remains a subset of output tokens, and raw usage is preserved.
This does not change prices or settlement rules.

This is a compatibility slice, not a production provider switch. It changes no
model, inference setting, spending cap, reservation rule, credential handling,
retry policy, prompt or memory behavior. The direct paid comparison adapter and
its experiment-accounting dependencies require a separate review; they are not
included here.

Validation: 47 targeted runner and telemetry tests passed. One existing closeout
assertion was excluded after reproducing the same failure on the untouched base:
`test_closeout_counts_parallel_write_before_completion` expects a receipt without
the callback fields that the base implementation already returns. No provider
requests were made, and the unrelated assertion was not changed.
