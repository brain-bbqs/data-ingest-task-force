---
name: lab-conversion-plan
description: Turn a completed lab intake into a reviewable conversion plan for a BRAIN-BBQS dataset, so the agent writing the conversion scripts implements the requester's decisions well. The requester owns the strategy, above all which data standard to target (NWB, or BIDS BEP047 for raw behavioral audio and video). This skill pins that decision down, maps every source file to its standardized destination, and drafts an example of how the expected output appears. Use it after lab-intake for any new lab or project, and also standalone when someone asks what the standardized output of a conversion would look like. The plan needs the requester's sign-off before lab-scaffold builds anything.
---

# Lab conversion plan

Produce the document a human signs off on before any scaffolding happens: which standard, how every source file maps into it, and what the output will look like. The kemere setup log (`labs/kemere/prompts/initial.md`) is the model for all three parts.

The plan exists for the coding agent, not the requester. Its purpose is to make the eventual conversion scripts correct: every mapping row, identity rule, and metadata field written down here is one the code will not have to guess at. It is not a vehicle for the agent to steer strategy. The requester is the main specification for what the conversion should be, above all which standard it targets.

Work from the intake record. If there is no intake yet, run the lab-intake skill first.

## Step 1: Pin down the standard decision

The target standard is the requester's decision. Treat the standard the intake names as the specification, and read `references/standards.md` to understand what implementing it entails.

- Standard named in the intake: adopt it. If the data seems to fit it badly, raise that as a question alongside the plan. The requester's call stands.
- No standard named: propose one as a recommendation, with a short justification grounded in the decision guide and the precedent labs, and mark it clearly as awaiting the requester's decision at sign-off. Do not build past the plan on an unconfirmed proposal.

Pin down the output granularity the same way. One NWB file per session is the default. Precedented variations exist for good reasons: a raw plus processed pair per session (shepherd), one file per subject-walk (inman). Note which one applies and why, and flag it for sign-off when it is a real choice rather than a consequence of the data.

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

Assemble steps 1 through 4 into one plan and present it for review, open questions first and any standard or granularity recommendation clearly marked as the requester's to decide. Do not run lab-scaffold until the requester approves. Quote the approval and any corrections into `labs/<lab>/prompts/initial.md` as further `## Request N` sections, so the record explains why the lab looks the way it does.
