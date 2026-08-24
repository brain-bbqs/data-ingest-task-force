---
name: lab-conversion-plan
description: Turn a completed lab intake into a reviewable conversion plan for a BRAIN-BBQS dataset. Chooses or confirms the target data standard (NWB, or BIDS BEP047 for raw behavioral audio and video), maps every source file to its standardized destination, and drafts an example of how the expected output appears. Use it after lab-intake for any new lab or project, and also standalone whenever someone asks which standard fits some data or what the standardized output of a conversion would look like. The plan needs human sign-off before lab-scaffold builds anything.
---

# Lab conversion plan

Produce the document a human signs off on before any scaffolding happens: which standard, how every source file maps into it, and what the output will look like. The kemere setup log (`labs/kemere/prompts/initial.md`) is the model for all three parts.

Work from the intake record. If there is no intake yet, run the lab-intake skill first.

## Step 1: Settle the standard

Read `references/standards.md` for how this repository uses NWB and BIDS, and for the decision guide.

If the intake names a standard, verify the fit rather than assuming it. Raise a mismatch as a question for the requester, not a silent override. If no standard is named, propose one with a short justification.

Settle the output granularity at the same time. One NWB file per session is the default. Precedented variations exist for good reasons: a raw plus processed pair per session (shepherd), one file per subject-walk (inman). Note which one applies and why.

## Step 2: Map every source file

Write a mapping table from the verbatim source tree to the standardized output. Every file and extension in the tree gets a row, including the ones deliberately left out. Three fates are allowed:

- converted into an output file,
- merged into another output's metadata (a BIDS sidecar block, an NWB field),
- out of scope, which the converter must still report rather than silently skip.

The kemere table is the reference shape:

| Source | Output |
| --- | --- |
| `07102026-Session1/` | `ses-20260710` (ISO date, `sNN` suffix for a 2nd+ session per day) |
| `overhead_video.mp4` | `sub-multi_ses-20260710_recording-overhead_video.mp4` |
| `overhead_video.settings` | merged into the video sidecar under `TrackingSettings` |
| `notes.txt`, `*.srt` | out of scope, reported and ignored |

Derive the identity rules while doing this: how the subject label and the session label are computed from the tree, and what sanitization applies (DANDI labels are alphanumeric). Present these as documented decisions that are easy to change, and plan for each to live in a single function once they reach code (kemere's `derive_session_label` is the precedent).

## Step 3: Draft the expected output example

Show concretely what the conversion will produce. This draft later becomes the golden test fixture (`tests/expected_output/`) or, where a full golden tree is impractical, the target-structure section of `code/README.md`.

- For BIDS: the full output tree for one session, plus one example sidecar JSON with realistic field values.
- For NWB: the output file layout (DANDI keeps assets directly under `sub-<label>/`, with the session in the filename and no `ses-` subfolder), plus an indented outline of each file's internal structure. `labs/shepherd/code/README.md` shows a real outline.

`references/standards.md` ends with example shapes for both.

If the intake already includes an expected-output example, reproduce it in the plan and reconcile the mapping against it. Any difference is a question for the requester, not something to paper over.

## Step 4: Draft the metadata plan

List which metadata lands where, and what is still `PROVISIONAL`:

- DANDI-required subject fields: species, sex (`M`/`F`/`O`/`U`), age (ISO 8601 duration) or date of birth.
- Session fields: start time with timezone, description, experimenters, institution, lab.
- Papers from the intake, as `related_publications` DOI links (NWB) or dataset-level references (BIDS).
- Device, electrode group, and channel-map details for data with neural channels.

For NWB targets this list is the skeleton of the lab's future `code/config.yaml`. `labs/inman/code/config.yaml` is the house pattern, including its `PROVISIONAL` markers and its header pointing at the NWB GUIDE.

## Step 5: Get sign-off

Assemble steps 1 through 4 into one plan and present it for review, open questions first. Do not run lab-scaffold until the requester approves. Quote the approval and any corrections into `labs/<lab>/prompts/initial.md` as further `## Request N` sections, so the record explains why the lab looks the way it does.
