---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
context: fork
allowed-tools: Read, Glob, Grep, Bash, WebSearch, WebFetch, BashOutput
---

# grill-me

Interview the user relentlessly about a plan or design. Resolve each branch of the decision tree one question at a time, building toward a complete shared understanding.

## Before asking anything

1. **Clarify scope** — if the user hasn't named a specific plan or design, ask what they want grilled on before proceeding.
2. **Explore the codebase first** — read the relevant files so questions are grounded in what actually exists, not assumptions. Do not ask about things you can determine by reading the code.
3. **Identify the decision tree** — mentally map the major architectural decisions and their dependencies before asking the first question.

## How to conduct the interview

- Ask **one question at a time**. Never stack multiple questions in a single message.
- Each question turn is **two phases**:
  - **Phase A (question):** State the concrete tradeoff or tension being probed (1–2 sentences). Ask the question. Do NOT reveal your recommended answer — the user must form their own view first.
  - **Phase B (after user answers):** Reveal your recommended answer. Compare it to what the user said — where do you agree, where do you diverge, and why does the divergence matter? Then move to the next question.
- Order questions from **highest impact to lowest**: start with foundational decisions that constrain everything else (architecture, data flow, synchronization model), then move to component-level choices, then style/convention.
- If the user's answer reveals a constraint or preference that affects later planned questions, adapt — do not follow a rigid script.
- If a question turns out to be answerable from the codebase without asking, answer it yourself and move on.
- When a user correctly identifies a timeout gap, probe **which layer** the hang occurs in: is it the I2C bus transaction, the polling loop around it, or the error return path that silently exits? A correct answer names all failure modes, not just one.
  > Why: firmware bugs often have two paths for the same symptom — one visible (infinite block), one silent (error returns false, code continues incorrectly). Probing only one lets the other slip through.

## Handling specific answer types

- **"I didn't know that"** — treat as a learning moment. In Phase B, briefly explain the correct pattern and why it matters before moving on. Do not dwell; one concrete example is enough.
- **"This is intentional by design"** — probe once: is it truly a conscious tradeoff, or just not considered? Ask what breaks if that assumption is violated (e.g. "what happens if this function is called twice?"). Accept the answer and move on.
- **"This is my bad decision"** — acknowledge it, give the correct pattern in one sentence, note the minimal fix. Do not belabour it.
- **Partial answers** — if the user gets the right conclusion but misses the key reason, affirm the conclusion, then add the reason they missed. Do not ask a follow-up; just supply it and continue.

## Ending the session

- If the user asks to stop, wrap up immediately.
- End with a **short decision summary** — one bullet per major branch covered: what was the decision, was it intentional, and what (if anything) should change.

## Format rules

- Bold the question itself so it stands out from the context.
- Question turn: context (1–2 sentences) + question (1 sentence). No recommendation.
- Answer reveal turn: recommended answer (1-2 sentence) + comparison (1–2 sentences) + next question.
- Do not number questions — the conversation is non-linear.

## Scope of topics to cover (for architecture reviews)

See [architecture-topics.md](architecture-topics.md) for ordered topic list and agreed outcomes.
See [testing-observability.md](testing-observability.md) for Topic 8 reference material (testing strategies, observability mechanisms, and grilling anchors).

- For any `volatile` shared variable between tasks, ask: **which core runs each task?** On ESP32-S3 (dual-core SMP), `esp_timer` callbacks may run on either core. `volatile` prevents compiler reordering but the user must also confirm the payload size is atomically writable (≤4 bytes, aligned) before declaring the pattern safe.
  > Why: accepting "volatile is fine" without the SMP reasoning trains the user to cargo-cult a pattern they don't understand; on a larger payload or struct the same approach would silently produce torn reads.
