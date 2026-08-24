---
name: lab-lessons
description: Encode lessons from a conversion back into the new-conversion skills so the next lab benefits. Use it at the end of every conversion, after lab-register, and also mid-conversion the moment a skill's guidance proves wrong, stale, or incomplete in practice, or when a strategy or solution worked out better than what the skills recommend. Generalizes each lesson into the smallest durable edit to the right file, keeps lab-specific quirks out of the shared skills, and routes strategy-level changes to the requester for sign-off.
---

# Lab lessons

The new-conversion skills stay useful only if every conversion feeds back what it taught. The skills were themselves distilled from the first labs (the no-`ses-`-subfolder rule came from inman, the nested project layout from suthana, the verbatim-port rules from shepherd). Closing each conversion by encoding its lessons keeps that distillation current instead of frozen at the labs that existed when it was written.

Run this at the end of every conversion. Do not wait for the end when guidance is actively wrong: fix the skill the moment reality disagrees with it, in the same branch, rather than deferring to a cleanup that never comes.

## What counts as a lesson

- A claim in a skill or reference that practice proved wrong or stale. A BEP047 detail that changed upstream, a DANDI validation rule, a CI step that moved. Fix the text in place. Do not append a correction note under the old claim.
- A first precedent that changes a default. The first lab needing a new standard, layout, container base, or test pattern. Add the row or precedent pointer where that decision is made.
- A step everyone performs that no skill names. Add it to the checklist it belongs to.
- A trap that cost real time. One line at the point of decision, phrased as the general rule with the lab as precedent, the way the no-`ses-`-subfolder rule is written.
- A better strategy or solution than the skills currently recommend. See the sign-off rule below before changing recommendation text.

## What does not belong in the skills

Route these elsewhere instead of accumulating them:

| It is | It goes to |
| --- | --- |
| Lab-specific, generalizes to nothing | That lab's `README.md` (rough edges, notes) |
| Registration or operational state | The notes in `dispatch/README.md` |
| Narrative of what happened and why | The lab's `prompts/` log, verbatim |
| Already documented in a canonical repo file | A pointer to that file, not a copy |

## How to edit

- Make the smallest durable edit that would have prevented the miss. Prefer tightening an existing sentence over adding a new one.
- Generalize or drop. A lesson that cannot be phrased as a rule the next lab can act on is a lab quirk. Route it per the table above.
- The skills describe the current best way, not their own history. Git history is the changelog. Delete guidance that no longer earns its place rather than layering qualifications onto it.
- Keep each `SKILL.md` lean. If a reference file has grown past usefulness, prune it in the same edit.

## Who decides

The division of authority from lab-conversion-plan applies here too:

- Mechanical and factual corrections (a wrong path, a stale spec detail, a missing checklist step): make them directly. The conversion's PR review covers them.
- Strategy-level guidance (the decision guide, defaults like output granularity, anything shaping what a future requester will be recommended): propose the edit and mark it for the requester's sign-off in the PR. The requester owns strategy for future labs the same way they own it for the current one.

## Where it lands

Commit skill edits on the same branch as the conversion that taught them, as their own commit, so reviewers see each lesson next to the work that produced it. Name the motivating experience in the commit message.
