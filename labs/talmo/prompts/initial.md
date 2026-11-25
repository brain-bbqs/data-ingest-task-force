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
- lab-conversion-plan: drafted [`conversion-plan.md`](conversion-plan.md). Stopped here for review, as asked.
