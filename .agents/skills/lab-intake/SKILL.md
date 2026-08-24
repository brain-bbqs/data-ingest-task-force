---
name: lab-intake
description: Normalize a new BRAIN-BBQS lab or project description into a structured intake record before any conversion work starts. Use this first whenever someone asks to set up, add, port, or convert data for a new lab or project in this repository, or pastes a description of lab data such as associated papers, a source-data file tree, metadata, dandiset ids, a target data standard, or prior conversion scripts. Runs before lab-conversion-plan, lab-scaffold, and lab-register.
---

# Lab intake

Turn a free-form description of a new lab's data into a structured intake record, record the request verbatim, and surface what is still missing. This is the first of the new-conversion skills. The chain is lab-intake, then lab-conversion-plan, then lab-scaffold, then lab-register, with lab-lessons feeding what the conversion taught back into the skills at the end.

Nothing in this skill converts data or writes conversion code. Its products are the started `prompts/` record, the filled intake record, and an honest list of open questions.

## Step 1: Record the request verbatim

Every lab directory preserves the prompts that drove its conversion under `labs/<lab>/prompts/` (`labs/kemere/prompts/initial.md` is the fullest example). Start that record now, in the working tree, so it lands with the eventual scaffold.

1. Create `labs/<lab>/prompts/README.md` with a `# Prompts` heading and the standard line "Collection of AI agent prompts given for this conversion."
2. Create `labs/<lab>/prompts/initial.md` containing
   - a `# Session: <short description of this setup>` title,
   - a one-paragraph summary of what the session is doing,
   - one `## Request N — <short label>` section per request so far, quoting the request verbatim in `>` blockquotes,
   - a note like `(Attached: <file names> from <origin>.)` after a quote when files were attached.
3. Append each later follow-up as a new `## Request N` section as the session continues. Decisions and corrections from the requester belong here too, quoted, so the record explains the final shape of the lab.

A lab expected to contribute more than one distinct data collection nests one directory per project, so the path becomes `labs/<lab>/<project>/prompts/` (see `labs/suthana/in-lab/`). If the description hints at sibling collections, ask before choosing the flat layout. Renaming later means churn across the dispatch registry and CI.

## Step 2: Extract the facts

Fill in `references/intake-template.md` with everything the description answers. Read any attached papers, trees, metadata files, and scripts before filling it in. Paste source-data trees verbatim rather than paraphrasing them.

Rules while filling it in:

- Do not guess. A field the description does not answer stays open.
- A value needed to keep work moving but not confirmed by the lab gets the house marker `PROVISIONAL`, with a note of what would confirm it. The marker must survive into whatever file the value lands in later, so nobody mistakes a placeholder for real metadata. `labs/inman/code/config.yaml` shows the pattern.
- Record who authored any prior conversion code, and whether it should be ported verbatim as provenance or improved on the way in. Original authors are credited in the lab README (see `labs/shepherd/README.md`), and the port mode changes how lab-scaffold treats the files.

The filled record itself is a working document for this session. It is not committed as a separate file. Its facts get folded into the lab's READMEs and `config.yaml` by lab-scaffold, while `prompts/initial.md` preserves the verbatim inputs.

## Step 3: Gap check

Compare the filled record against the "Minimum to proceed" checklist at the bottom of the template, then split what is missing into two lists.

- Blocking. The conversion plan cannot be drafted without it. Examples: no source tree at all, no idea what the recordings contain, no species.
- Deferrable. Work proceeds with a `PROVISIONAL` placeholder or an open question. Examples: unassigned dandiset ids, exact session start times, electrode coordinates, unconfirmed institution.

## Step 4: Deliver

Present the filled intake record and a numbered list of open questions, blocking ones first. If nothing blocks, continue with the lab-conversion-plan skill. If something blocks, stop and ask. When answers arrive, quote them into `prompts/initial.md` like any other request.
