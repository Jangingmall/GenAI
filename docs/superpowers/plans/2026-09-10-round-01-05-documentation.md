# Round 01–05 Five-Artifact Documentation and Index Restoration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the five flat Round 01–05 experiment logs into five self-contained artifact documents per round and restore the experiment index using the verified facts table.

**Architecture:** Each round becomes a directory containing implementation, error, experiment, inference-API, and BE/FE-interface logs. The existing report remains a compact index and summary; Round 06–09 files are outside this worker’s ownership, so their expected five-document links are indexed without editing their content.

**Tech Stack:** Markdown, repository pilot JSON, `scripts/check_plan_diversity.py`, `scripts/check_cutout_fidelity.py`, Git read-only checks.

**Spec:** `.orchestration/briefs/round-5doc-spec.md` and `.orchestration/briefs/round-facts-verified.md`

## Global Constraints

- Use `.orchestration/briefs/round-facts-verified.md` as the sole source of round metrics.
- Keep the A/B/C sections of `docs/deliverables/03-second-experiment-report.md` unchanged.
- Record facts in past tense; do not invent human-review scores or future recommendations.
- Do not rerun pilots or models, modify source/tests/scripts/data/generated assets, or commit/push.
- Record `참고용` label omission as an unresolved, intentionally unmodified deployment blocker.

---

### Task 1: Map the existing Round 01–05 logs into five artifacts

**Files:**
- Read: `docs/deliverables/experiments/round-01.md` through `round-05.md`
- Read: `.orchestration/briefs/round-5doc-spec.md`, `.orchestration/briefs/round-facts-verified.md`
- Create: `docs/deliverables/experiments/round-0N/01-implementation-checkpoint.md` through `05-be-fe-interface.md` for N=01..05
- Delete after migration: the five flat `round-0N.md` files

**Interfaces:**
- Consumes: each flat round log plus verified metrics and execution metadata.
- Produces: five logs per round, each beginning with the required metadata table and containing only facts from that round.

- [x] **Step 1: Preserve the source facts in a migration map**

  For each N=01..05, retain the pilot path, predecessor path, image-generation status, verified metrics, and the changed-file facts from the flat log. Treat `round-facts-verified.md` as authoritative when the flat log conflicts.

- [x] **Step 2: Write the implementation checkpoint**

  Start with the required metadata table, then record changed files at symbol/line granularity where verified, tests passed when recorded, and any new catalog/script/CSS artifact.

- [x] **Step 3: Write the error analysis**

  Use five subsections for each incident: `증상`, `증거`, `원인`, `조치`, `재발 방지`. Include unchanged carried-over defects when that round had no new error.

- [x] **Step 4: Write the experiment report**

  Include the sequence `문제 → 가설 → 실험 설계 → 실행 명령 → 측정 수치 → 판정 → 입증/반증 → 남은 한계`, using the verified table’s average Jaccard, effective common count, identical pairs, unique sequences, length distribution, cutout gate, and duration.

- [x] **Step 5: Write the inference and interface logs**

  For unchanged areas, use `## 변경 없음` and summarize the maintained contract in 3–5 lines. For changed areas, record prompt/API/provider effects and the BE/FE schema compatibility facts.

### Task 2: Restore the overall experiment index

**Files:**
- Modify: `docs/deliverables/03-second-experiment-report.md` after the unchanged A/B/C sections

**Interfaces:**
- Consumes: the 9-round verified facts and expected five-document paths.
- Produces: one-line 1–9 table, links to all 45 artifact logs, the three-part root cause and Round 09 final result.

- [x] **Step 1: Replace stale flat-round links**

  Point Round 01–05 rows to `experiments/round-0N/01-implementation-checkpoint.md` through `05-be-fe-interface.md`; point Round 06–09 rows to the corresponding nested paths owned by the parallel worker.

- [x] **Step 2: Correct the index metrics**

  Use effective common-block counts (excluding `hero`/`closing`), 5/6 success for Round 07, `--image-provider none` for Rounds 07–08, and case-level Flux image generation for Rounds 06 and 09.

- [x] **Step 3: Keep the required conclusions and unresolved facts**

  State the three-part root cause, the unsupported acceptance criterion as the longest-running error, the final Round 09 metrics, missing human scores, unrun 60-case evaluation, and intentionally unresolved `참고용` display omission.

### Task 3: Verify the documentation migration

**Files:**
- Read: all created logs and the index
- Read: saved pilot outputs and verification scripts

- [x] **Step 1: Check headings and metadata**

  Verify every Round 01–05 directory has exactly five files, every file has the required metadata table, and every required section is present in the specified order.

- [x] **Step 2: Check links and preservation**

  Verify all 45 nested links resolve, the A/B/C report prefix is byte-identical to `HEAD`, and no flat Round 01–05 files remain.

- [x] **Step 3: Run read-only factual checks**

  Run `git diff --check`, `scripts/check_plan_diversity.py` only against saved pilot directories, and the existing cutout gate against saved outputs; record results in the task report without rerunning a pilot.
