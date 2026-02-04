Not difficult at all—and it fits really naturally with the **Spec → Brief → Draft** pipeline. You just add a small “spec completion” step that decides whether to ask a follow-up question (or fill sensible defaults).

The trick is to make it **deterministic and low-friction** so the user doesn’t get stuck in back-and-forth.

---

## The pattern: Spec Completion + Clarifying Questions

### Step 1: Generate a draft `ReportSpec` + detect missing fields

When the user prompt is vague (“write something fun about this week”), the agent produces:

* a **partial spec** (with defaults)
* a list of **missing/ambiguous fields** that materially affect output

### Step 2: Decide: ask vs assume defaults

Use a simple rule:

* If missing info would change the *structure* or *tone* significantly → **ask**
* If it’s minor → **assume defaults** and proceed

Examples of “ask-worthy” ambiguity:

* Article type is unclear (recap vs power rankings vs deep dive)
* Tone constraints matter (friendly vs savage roasting)
* Time range unknown (which week?)
* “Bias” requested but target/intensity unclear

Examples of “default-worthy” ambiguity:

* Exact word count (use a standard)
* Minor section ordering
* Small stylistic preferences

### Step 3: Ask 1–3 targeted questions max

Keep it tight. You’re aiming for **one turn**.

Good format:

* multiple-choice where possible
* include defaults (“If you don’t care, I’ll do X”)

---

## Integration options (choose one)

### Option A (recommended): A tiny “Spec Interview” mode in your runner

Your runner orchestrates:

1. `spec_synthesis()` → returns `{spec, questions?, ready}`
2. If `ready=false` → show questions to user, collect answers
3. `spec_finalize(spec, answers)` → final spec
4. Continue to `brief → draft → verify`

**Why this is great**

* Very reliable and easy to debug.
* You can enforce “ask at most once” policy.
* You can persist partially-filled specs.

### Option B: Let the agent ask questions inside the conversation

Single agent handles it naturally:

* If spec incomplete, it asks questions before calling tools.

**Why it’s simpler**

* Fewer moving pieces.

**Tradeoff**

* Harder to enforce strict “max 1 turn of questions” and avoid rambling.

In practice, Option A is cleaner for a CLI/web app.

---

## What the clarifying prompt should look like

You’ll get the best results if you standardize the “spec interview” questions to a small set of levers:

1. **What are we writing?** (format)

* Weekly recap
* Power rankings
* Team deep dive (choose team)
* Playoff reaction
* Custom (describe)

2. **What time range?**

* Week N
* Weeks N–M
* Since last report

3. **Voice/tone**

* Straight sportswriter
* Hype / celebratory
* Snarky / roast-light
* Savage roast (opt-in)
* Other: ______

4. **Bias (optional)**

* None
* Favor: [team(s)]
* Clown: [team(s)]
* Intensity: 1–3

5. **Length**

* Short (~400–600)
* Medium (~800–1200)
* Long (~1500+)

If you ask just **3** questions, my go-to set is:

* format, time range, tone (and bias can be folded into tone if needed)

---

## How this plays with presets and “true flexibility”

Even if the user wants something novel (“noir detective waiver investigation”), you can still ask:

* time range
* how mean/snarky
* any must-include teams/angles

Then compile into `ReportSpec` and proceed.

---

## Implementation details (Agents SDK-friendly)

### Add two schemas

* `ReportSpecDraft` (allows missing fields)
* `ReportSpec` (fully resolved with defaults)

### Add a “spec completeness” function

This is deterministic Python:

* check required keys based on `article_type`
* if missing, produce question set

### Add a “question budget”

Hard cap:

* 1 round
* 1–3 questions
* if user doesn’t answer everything, fill defaults and proceed

This prevents the agent from becoming annoying.

---

## UX tip: provide defaults inline

Instead of “what tone?”, ask:

> Tone: straight / hype / snark (default: hype)

This makes users feel like they’re configuring, not being interrogated.

---

## Bottom line

Integrating a spec-follow-up flow is straightforward and plays perfectly with your architecture. It’s basically a small pre-step that outputs either:

* a complete spec, or
* a minimal set of questions to complete it.

If you want, I can draft:

* the `ReportSpec` / `ReportSpecDraft` Pydantic models,
* a `spec_completeness()` function shape,
* and a template for the “spec interview” prompt + example CLI interaction.
