---
name: debug-session
description: Diagnose ESP32/ESP-IDF firmware failures from serial output or described symptoms. Maps log patterns to root causes and guides fixes. Use when the firmware crashes, hangs, produces wrong output, or behaves unexpectedly.
allowed-tools: Read, Glob, Grep, Bash, WebSearch, WebFetch
---

# debug-session

Diagnose ESP-IDF firmware failures. Work from evidence — serial output, symptoms, or both — to root cause and fix.

1. state the most likely cause



## On entry

1. If the user pastes a log: parse it immediately — do not ask for more info unless critical context is missing.
2. If the user describes a symptom without a log: ask for the serial output first. One request only — if they can't provide it, work from the symptom.
3. Read the relevant source files before suggesting any fix. Never suggest a fix based on the pattern alone without checking the actual code.

## Diagnosis workflow

1. **Identify the failure class** — see [patterns.md](patterns.md) for ESP-IDF error signatures and their root causes.
2. **Anchor to the code** — grep/read the files implicated by the log (function names, addresses, component names in the output).
3. **State the root cause** — one sentence. If uncertain, say so explicitly.
4. **show the evidence in the code** - Identify the lines in the files that causes the failure.
5. **suggest one small experiment**
6. **Propose the fix** — show the exact change needed. If multiple causes are plausible, list them ranked by likelihood before picking one.
7. **Verify** — after the user applies the fix, ask what the new output is. Do not declare the bug fixed until you have seen confirming evidence.

## Rules

- Never guess a fix without reading the relevant source file first.
- If the log contains a backtrace or PC address, always attempt to decode it — ask the user to run `xtensa-esp32s3-elf-addr2line` if symbols are available.
- If the symptom is a hang with no output, ask: does the watchdog trigger eventually? This distinguishes a true deadlock from a very slow operation.
- If the symptom is wrong data (not a crash), check the data path end-to-end: sensor read → computation → print format → consumer parsing.
- State confidence level when the cause is inferred rather than directly evidenced.

## Format

- Root cause: one sentence, bold.
- Evidence: quote the exact log line(s) that led to this conclusion.
- Fix: code diff or precise description of what to change and where.
- Next step: one sentence — what to check after applying the fix.
