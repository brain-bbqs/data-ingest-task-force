# Open questions

The questions this conversion still depends on, and where their answers land. Numbers match the conversion plan in [`prompts/conversion-plan.md`](prompts/conversion-plan.md), so they stay citable from follow-up PRs, commit messages and the `PROVISIONAL` comments in `code/config.yaml`. Q11 to Q13 were added after the plan.

When a question is answered, quote the answer into `prompts/initial.md` as a new request, make the change, and move the entry to "Resolved" below.

## Status at a glance

| # | Question | Status | Blocks |
| --- | --- | --- | --- |
| [Q6](#q6-camera-timing-in-slap-2m) | Are the SLAP-2M cameras hardware-triggered? | Implemented as assumed, unconfirmed | `StartTime` of SLAP-2M videos |
| [Q8](#q8-three-stray-analysis-files) | What are the three `.slpanalysis.h5` files? | Implemented as proposed, unconfirmed | Three files left out |
| [Q9](#q9-metadata-nobody-supplied) | Ages, SLAP-2M animals, authors, license, institutions | Waiting on the lab or the preprint | DANDI-ready metadata |
| [Q10](#q10-2d-track-identity) | Which 2D track is which mouse in MouseDyad-10M? | Waiting on the lab | Per-animal use of the 2D files |
| [Q11](#q11-triangulation-tool) | Which tool made the 3D? | Waiting on the lab or the preprint | `GeneratedBy` of `derivatives/triangulation` |
| [Q12](#q12-validation-not-yet-run) | BIDS validator and DANDI upload behavior | Deferred to the first real run | Upload |
| [Q13](#q13-derivative-names-and-model-placement) | Derivative dataset names and where the models sit | Implemented as understood, unconfirmed | Output paths |

## Waiting on the lab or the preprint

### Q9. Metadata nobody supplied

The preprint ([doi:10.64898/2026.11.17.767188](https://doi.org/10.64898/2026.11.17.767188)) could not be read from the build sandbox, because `biorxiv.org`, `doi.org` and `crossref.org` are outside its network allowlist. What follows comes from the lab's dataset cards on Hugging Face.

- **Known now:** MouseDyad-10M is 9 CD-1 mice (4 male, 5 female) in 18 pairings, with track 0 the male. SLAP-2M is eight CD-1, four C57BL/6J and four BALB/c mice. Both cards carry `license: mit`.
- **Ask the lab, or read from the preprint:** ages or dates of birth. The sex and identity of the SLAP-2M animals, and which coat color is which strain. The full author list. Whether MIT is the license they want on EMBER. The recording institution of each collection (the cards say Murthy lab for MouseDyad-10M and Falkner lab for SLAP-2M, both Princeton, while paths inside the MouseDyad-10M files name a Falkner lab server). Camera make and model. The timezone of the timestamps. The meaning of `experimental_code` (`ACL2MSFSd/e/m/p`).
- **Current handling:** `participants.tsv` has `sex` as `n/a` and no age. `authors`, `license` and `institution` in `code/config.yaml` are `PROVISIONAL`.

### Q10. 2D track identity

The 3D files name their tracks by animal. The 2D files say `track_0` and `track_1`.

- **Ask the lab:** is 2D `track_0` always the male, as in the 3D?
- **Current handling:** the 2D sidecars state that the order is unconfirmed.

### Q11. Triangulation tool

- **Ask the lab:** which tool and version triangulated and smoothed each collection's 3D?
- **Current handling:** `generated_by.triangulation` in `code/config.yaml` names sleap-anipose (MouseDyad-10M) and LUC3D (SLAP-2M), both `PROVISIONAL`.

## Implemented, unconfirmed

### Q6. Camera timing in SLAP-2M

BEP047 requires `StartTime` on every file with a `recording` entity. The requester assumes all cameras share one time stream. The MouseDyad-10M card says "hardware-synchronized". The SLAP-2M card says only "synchronized".

- **Checked:** no file in the deposit holds per-frame timestamps or per-camera offsets. Video timestamps are evenly spaced in both collections. SLAP-2M cameras of a session have identical frame counts. The per-camera timestamps in SLAP-2M file names differ by 6 to 18 s within a session, which reads as file creation order.
- **Current handling:** `StartTime: 0` everywhere, with the source timestamp kept in each sidecar's `Synchronization` block.
- **Ask the lab:** were the SLAP-2M cameras hardware-triggered, so that frame N is simultaneous across cameras?

### Q8. Three stray analysis files

SLAP-2M sessions `10212022175626` (top, topL) and `10212022181154` (back) each hold a `*.predictions.proofread.slpanalysis.h5` beside the regular `*.predictions.proofread.slp.analysis.h5`.

- **Current handling:** reported in the run summary and not converted.

### Q13. Derivative names and model placement

The requester asked for models under `derivatives/models` "unless each is one to one with the .slp output in which case bundle it closer to the `derivatives/pipeline-SLEAP` entry".

- **Current handling:** each collection ships one centroid and centered-instance model pair, and the provenance in the MouseDyad-10M `.slp` files names exactly that pair. So the models sit in `derivatives/sleap/models/`, beside the files they produced. The derivative datasets are named `derivatives/sleap` and `derivatives/triangulation`.
- **To confirm:** whether `derivatives/sleap` is the intended name, and whether one model pair per collection counts as one to one. The names are constants at the top of the converter. The SLAP-2M side-camera model is not in the deposit.

## Deferred

### Q12. Validation not yet run

- The BIDS validator has not been run on `rawbids/` against the BEP047 schema, nor on the study root.
- The `_pose` and `_calibration` suffixes of the derivatives are not in the BIDS schema. A `.bidsignore` may be needed.
- Whether `dandi upload` accepts a study dataset with these derivatives is unknown. Both projects are registered with the default `upload_validation`, so a refused upload fails the run visibly. Switching to `ignore` is the requester's call.
- The MouseDyad-10M session `20250904_183921` has corrupted 3D and is left out of the lab's public release. It is converted here and flagged in `sessions.tsv`. Decide whether it should be excluded.

## Resolved

| # | Question | Answer | Where |
| --- | --- | --- | --- |
| Q1 | Where the raw BIDS dataset sits | Top-level `rawbids/` | Request 2 |
| Q2 | Subject model | One subject per unique pair of animal IDs in MouseDyad-10M. SLAP-2M has no IDs and stays `sub-multi`. | Request 2 |
| Q3 | Pose format | Native `.slp` and others for now. NWB later. | Request 2 |
| Q4 | One derivative dataset or several | Split by pipeline (see Q13 for the names) | Request 2 |
| Q5 | Models | Kept, beside the SLEAP derivative (see Q13) | Request 2 |
| Q7 | Lab key | `talmo` | Request 2 |
