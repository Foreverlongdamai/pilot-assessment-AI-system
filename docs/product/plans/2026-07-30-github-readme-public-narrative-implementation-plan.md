# GitHub README Public Narrative Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the GitHub repository understandable to a non-specialist reader by leading with motivation, representative training/assessment practice, the two 2015 PAV foundations, the proposed VR pilot-skill workflow, and the future public-download path while preserving the product's technical and scientific boundaries.

**Architecture:** This is a documentation-only change. The root README becomes the public narrative entry point; `docs/product/REFERENCES.md` records the additional primary sources; the product documentation index records the approved design and executed plan. No code, model, runtime, or release artifact changes.

**Tech Stack:** GitHub-flavoured Markdown, Mermaid, repository-local link checks, primary-source web references.

**Execution mode:** INLINE, as requested by the product owner. The documentation change does not use subagents and does not require software TDD.

---

### Task 1: Record the approved narrative and provenance

**Files:**
- Create: `docs/product/specs/2026-07-30-github-readme-public-narrative-design.md`
- Create: `docs/product/plans/2026-07-30-github-readme-public-narrative-implementation-plan.md`

- [x] **Step 1: Save the approved design**

Record the audience, narrative order, attribution rules, scientific boundaries, sources, and acceptance criteria from the approved 2026-07-30 conversation.

- [x] **Step 2: Confirm the task is documentation-only**

Run:

```powershell
git diff --name-only
```

Expected: only Markdown documentation files appear.

### Task 2: Add the missing public research references

**Files:**
- Modify: `docs/product/REFERENCES.md`

- [x] **Step 1: Add the companion 2015 PAV study**

Add Perfect, Jump, and White, *Handling Qualities Requirements for Future Personal Aerial Vehicles*, DOI `10.2514/1.G001073`, and state that it supports the flight-naive participant, response-type, task-performance, and handling-qualities context.

- [x] **Step 2: Add representative adjacent-domain sources**

Add official GOV.UK/DVSA pages for theory, hazard perception, and the practical driving test; the FAA Powered-Lift ACS and AC 194-2; and the original AAAI 2024 Virtual Driving Instructor paper. Mark the driving and powered-lift material as representative context rather than a universal or product-certification claim.

- [x] **Step 3: Check DOI and source presence**

Run:

```powershell
rg -n "G001073|30315|private_pl_acs_13|AC 194-2|hazard perception" docs/product/REFERENCES.md
```

Expected: every new source family has at least one match.

### Task 3: Rewrite the repository entry narrative

**Files:**
- Modify: `README.md`

- [x] **Step 1: Replace the first-screen introduction**

Lead with a one-sentence value proposition and the research title. Define the product in everyday language before using EvidenceRecipe, CPT, or sidecar terminology.

- [x] **Step 2: Add motivation and representative current practice**

Add a compact comparison covering road-driver training/testing, emerging simulator intelligent instructors, powered-lift task/Knowledge/Risk Management/Skill assessment, and PAV handling-qualities research. Link each factual description to the corresponding primary or official source.

- [x] **Step 3: Add accurate research lineage**

Name and attribute both 2015 Perfect/Jump/White papers. Describe the project as continuing this line under Professor Linghai Lu's guidance. Keep the 2016 Lu et al. paper as related landing-profile research rather than the main general-skill foundation.

- [x] **Step 4: Explain the VR workflow**

Add plain-language steps and a Mermaid flow from task definition and X/U/I/G/P/pilot-camera input through Evidence extraction and TaskScheme selection to Bayesian sub-skill/competency inference and traceable results.

- [x] **Step 5: Preserve the technical handoff**

Retain the current detailed sections for Bayesian arrow semantics, staged saves, system/project ownership, node/task editing, Python operator extension, data contracts, missing data, implementation status, documentation navigation, development verification, and product boundaries.

- [x] **Step 6: Add the final-product download boundary**

Link to the repository's GitHub Releases area and state that the eventual public release will provide a versioned portable ZIP, checksum, release notes, and manuals without user Project/Session data. Keep RC.4 identified as pending user acceptance and do not upload or relabel it as a final public release.

### Task 4: Register and verify the documentation change

**Files:**
- Modify: `docs/product/README.md`
- Verify: `README.md`
- Verify: `docs/product/REFERENCES.md`

- [x] **Step 1: Add the design and plan to the documentation index**

Record the 2026-07-30 public-narrative decision and link both new documents in the recommended-reading table.

- [x] **Step 2: Verify required public concepts**

Run:

```powershell
rg -n "为什么|汽车|Powered-Lift|2015|VR|Evidence|Bayesian|科学" README.md
```

Expected: all approved narrative elements are present.

- [x] **Step 3: Verify local Markdown links**

Parse all non-HTTP Markdown targets in the three modified Markdown documents, ignore anchors, and assert that every resolved path exists.

- [x] **Step 4: Review the final diff**

Run:

```powershell
git diff --check
git diff --stat
git status --short
```

Expected: no whitespace errors; only the planned Markdown files are modified or added.

- [x] **Step 5: Commit the coherent documentation change**

Run:

```powershell
git add README.md docs/product/README.md docs/product/REFERENCES.md docs/product/specs/2026-07-30-github-readme-public-narrative-design.md docs/product/plans/2026-07-30-github-readme-public-narrative-implementation-plan.md
git commit -m "docs: explain pilot assessment research motivation"
```

Expected: one documentation-only commit; pushing remains a separate explicit action unless already requested.
