You can get “true flexibility” without giving up reliability by treating **formats/styles as optional scaffolding**, and moving toward a **spec-driven workflow**:

* When the user asks for a known thing (“weekly recap”, “power rankings”), you apply a preset.
* When they ask for something novel (“write this like a noir detective investigating waiver fraud”), you **generate a report spec first**, then write from that spec.

That keeps the system extensible while still grounded in data and guardrails.

---

## The key idea: introduce a `ReportSpec` layer

In the future, don’t hardcode “formats/styles” as the only entry points. Instead:

1. **Interpret the user prompt → produce a `ReportSpec` (structured)**
2. **Use the `ReportSpec` to drive research + writing**

### What goes in `ReportSpec` (high level)

* `genre_voice`: e.g. “noir detective”, “sports radio rant”, “financial analyst note”
* `tone_controls`: snark level, hype level, profanity policy, seriousness
* `structure`: section list (or “freeform”), length, POV, narration constraints
* `content_requirements`: must mention standings implications, must cover top 3 matchups, etc.
* `bias_profile`: targets + intensity + boundaries
* `evidence_policy`: “every number must be cited from tools”, “no unverifiable injury claims”
* `audience`: league members, newcomers, commissioner, etc.

**Why this works**

* You can satisfy *any* creative request by mapping it into a spec.
* The spec becomes your safety rails: it defines what’s allowed and what must remain factual.

---

## How this coexists with presets

Think of presets as **default spec templates**.

* `weekly_recap` preset = a filled-out `ReportSpec`
* `power_rankings` preset = another filled-out `ReportSpec`

For a custom prompt:

* You start from a minimal base spec
* Let the agent expand it based on the user’s request

So presets never block flexibility—they just provide a starting point.

---

## A future-proof workflow (single agent, still)

### Phase A: “Spec synthesis”

Agent reads the user request and outputs `ReportSpec`.

* If the request matches a preset strongly → the spec references it and overrides a few fields.
* If not → it constructs a new spec with a proposed structure.

### Phase B: “Research to brief”

Using the spec, the agent calls tools and builds your existing `ReportBrief`.

### Phase C: “Draft”

Write from `ReportBrief` + `ReportSpec`.

### Phase D: “Verify”

Check draft claims against the brief and the spec’s evidence policy.

This gives you freedom in *shape* while keeping rigor in *facts*.

---

## How to implement “novel formats” safely (the guardrails)

True flexibility is where hallucinations and “style overpowering facts” tend to creep in, so you’ll want a few always-on constraints:

1. **Evidence gating**

* If the spec allows numbers, require them to come from tool outputs.
* If the user asks for “invented” things (“make up a fake scandal”), either:

  * refuse, or
  * clearly label as fiction (your choice), but keep it separate from real reporting.

2. **Fact vs framing separation**

* Facts come from the brief.
* Voice/bias only affects phrasing.

3. **Deterministic constraints**

* Limit max length, require a final “Key Facts” or “Scoreboard” appendix in factual tone.

  * This appendix is a great trick: it keeps engagement high while preserving trust.

---

## Practical tactics to enable flexibility over time

### 1) Add a “prompt router” (lightweight)

Before invoking the agent, classify the request:

* preset match?
* partially matches preset?
* novel/custom?

This can be:

* a tiny heuristic router, or
* a quick model call that outputs: `{mode: preset|hybrid|custom, chosen_preset?: ..., spec_overrides?: ...}`

### 2) Build a “style library” but don’t require it

Even in custom mode, you’ll benefit from a palette of reusable style components (sports radio, beat reporter, snark columnist). The spec can say:

* “use library style X” **or**
* “invent a style from prompt”

### 3) Save “successful custom specs” as new presets

When someone asks for “Shakespearean power rankings” and it’s a hit:

* store that spec as a named preset
* now it’s repeatable and testable

This is how you grow flexibility without chaos.

### 4) Add a “constraints-only” user interface

Let the user specify requirements without knowing your presets:

* “Make it 700 words, 3 sections, roast Team A lightly, focus on trades this week.”

That maps cleanly into `ReportSpec`.

---

## Minimal change to your current design doc

You’d add one folder + one schema, and tweak the workflow:

**New:**

* `agent/specs.py` (Pydantic `ReportSpec`)
* `prompts/spec_synthesis.md` (instructions to convert arbitrary user request → spec)
* optional `prompts/style_atoms/` (small reusable voice fragments)

**Workflow update:**

* Runner: `Request → Spec → Brief → Draft → Verify`

Everything else remains intact.

---

## Bottom line

To enable “true flexibility,” don’t try to predefine every format. Instead, make the agent **generate a structured spec for any request**, then use your existing brief-based reporting pipeline to keep it factual and tool-grounded.

If you want, I can draft:

* a concrete `ReportSpec` Pydantic model,
* the `spec_synthesis` prompt,
* and an example of how a weird prompt (“noir detective waiver-wire investigation”) compiles into a spec + brief + final article.
