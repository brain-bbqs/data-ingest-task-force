# Session: BIDS study conversion for the Talmo lab LUC3D deposits

Setting up the Talmo lab conversion. One incoming dandiset (`000641`) holds two LUC3D collections, `MouseDyad-10M` and `SLAP-2M`. Each becomes its own standardized BIDS study dataset, with the behavioral videos as a BEP047 raw BIDS dataset and the pose products under `derivatives/`. The session runs the new-conversion skills in order and stops for plan review before any code is written.

---

## Request 1 — Set up the conversion

> ```
> Please set up a new conversion for the Talmo lab, working through the
> new-conversion skills in .agents/skills/ in order: lab-intake, then
> lab-conversion-plan, then stop for my review of the plan before running
> lab-scaffold and lab-register. Finish with lab-lessons, encoding anything
> this conversion taught back into the skills.
> ```
>
>
> its one incoming dataset, 000641, two folders (luc3d/MouseDyad-10M, SLAP-2M)
>
> each folder to a separate standardized dataset (000643 and 000642) respectively
>
> BIDS-Study with the sourcedata being the BEP047 valid behavioral videos with as much metadata extracted as possible (similar to Kemere lab); then the pose and other details go to `derivatives/`

(No files were attached. The source tree and its metadata files were read from the archive, see the plan's "Evidence actually inspected".)

### What happened

- lab-intake: listed all 4,402 assets of `000641` through the archive API and read the lab's own READMEs, manifests, master sheets, QC tables, skeleton, calibration files, and one representative file of every other kind.
- lab-conversion-plan: drafted [`conversion-plan.md`](conversion-plan.md) and stopped for review, as asked.

---

## Request 2 — Plan decisions

> rawbids; an way to add ID to unique dyad based on unique combinations of subject IDs?; first pass less keep native .slp and other, will deal with NWB in the future; I assume via luc3d all cameras are on the same time stream but keep an eye on the supplementary file contents to see if they have anything like timestamps or offsets; yes, derivatives/models unless each is one to one with the .slp output in which case bundle it closer to the `derivatives/pipeline-SLEAP` entry; talmo is fine

### What happened

- Raw BIDS dataset moved to a top-level `rawbids/`.
- MouseDyad-10M subjects are now one per unique pair of animal IDs.
- Looked for timestamps and offsets in every kind of supplementary file: the SLEAP `.slp` files, the analysis and 3D `.h5` files, the calibration files, the QC tables and the video containers. None holds per-frame timestamps or per-camera offsets, and video timestamps are evenly spaced. `StartTime` stays 0.
- Each collection has one model pair behind its SLEAP output, so the models went to `derivatives/sleap/models/`. This reading of the request is recorded as Q13.

---

## Request 3 — The paper

> are oyu able to read the corresponding paper to get any of that other info?

### What happened

- Found the preprint, "LUC3D: Multi-animal 3D pose tracking in the browser" (bioRxiv, doi:10.64898/2026.11.17.767188). It could not be read, because `biorxiv.org`, `doi.org` and `crossref.org` are outside the sandbox's network allowlist.
- Read the lab's public dataset cards on Hugging Face instead (`talmolab/mouse-dyad-10M`, `talmolab/slap-2m`). They supplied strains, sexes, the animal ID format, the hardware synchronization of MouseDyad-10M, the license and the recording labs. Each value in `code/config.yaml` cites its source.
- lab-scaffold, lab-register and lab-lessons then ran. What is still missing is in [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).

---

## Request 4 — One derivative dataset, and per-subject information

> maybe put both under derivatives/pipeline-luc3d?
>
> did you get all the per subject info you needed?

### What happened

- The 2D pose, the 3D pose, the calibration and the models now sit in one derivative dataset, `derivatives/pipeline-luc3d/`. This resolves Q13.
- Per-subject information is incomplete. What is known and missing per animal is recorded as Q14 in [`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md).
