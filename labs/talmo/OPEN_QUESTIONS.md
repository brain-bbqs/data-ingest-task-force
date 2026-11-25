# Open questions

The questions this conversion still depends on, and where their answers land. Numbers match the conversion plan in [`prompts/conversion-plan.md`](prompts/conversion-plan.md), so they stay citable from follow-up PRs, commit messages and the `PROVISIONAL` comments in `code/config.yaml`. Q11 to Q14 were added after the plan.

When a question is answered, quote the answer into `prompts/initial.md` as a new request, make the change, and move the entry to "Resolved" below.

## Status at a glance

| # | Question | Status | Blocks |
| --- | --- | --- | --- |
| [Q6](#q6-camera-timing-in-slap-2m) | Are the SLAP-2M cameras hardware-triggered? | Implemented as assumed, unconfirmed | `StartTime` of SLAP-2M videos |
| [Q8](#q8-three-stray-analysis-files) | What are the three `.slpanalysis.h5` files? | Implemented as proposed, unconfirmed | Three files left out |
| [Q9](#q9-metadata-nobody-supplied) | Ages, SLAP-2M animals, authors, license, institutions | Waiting on the lab or the preprint | DANDI-ready metadata |
| [Q10](#q10-2d-track-identity) | Which 2D track is which mouse in MouseDyad-10M? | Waiting on the lab | Per-animal use of the 2D files |
| [Q11](#q11-triangulation-tool) | Which tool made the 3D? | Waiting on the lab or the preprint | `GeneratedBy` of the derivative dataset |
| [Q14](#q14-per-animal-metadata) | Age and identity of each animal | Waiting on the lab or the preprint | A complete per-animal record |
| [Q12](#q12-validation-not-yet-run) | BIDS validator and DANDI upload behavior | Deferred to the first real run | Upload |

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

### Q14. Per-animal metadata

What the deposit and the dataset cards give for each animal is incomplete.

- **MouseDyad-10M, known:** the 9 animal IDs, each animal's sex (from its track position, with the card's "track 0 is always the male"), the strain (CD-1), the number of tail marks per session, and which sessions each animal is in.
- **Genotype:** presumed wild type in both collections. The cards name only standard strains (CD-1, C57BL/6J, BALB/c) and no transgenic line. No source says so outright, so it is not written into `participants.tsv`.
- **MouseDyad-10M, missing:** age or date of birth, weight, housing, and whether the two animals of a pair were familiar.
- **SLAP-2M, missing:** everything per animal. The deposit has only the number of white, agouti and black mice per session. There are no animal IDs, so the 16 animals the card mentions cannot be told apart or matched to sessions, and no sex or age is given.
- **Current handling:** a subject is a pair (MouseDyad-10M) or `sub-multi` (SLAP-2M), so `participants.tsv` has `sex` as `n/a`. The MouseDyad-10M animal IDs and sexes are in the `male_id` and `female_id` columns. There is no one-row-per-animal table.
- **Ask the lab:** a table with one row per animal (ID, sex, date of birth, strain), confirmation that all animals are wild type, and for SLAP-2M the animal IDs present in each session.

## Implemented, unconfirmed

### Q6. Camera timing in SLAP-2M

BEP047 requires `StartTime` on every file with a `recording` entity. The requester assumes all cameras share one time stream. The MouseDyad-10M card says "hardware-synchronized". The SLAP-2M card says only "synchronized".

- **Checked:** no file in the deposit holds per-frame timestamps or per-camera offsets. Video timestamps are evenly spaced in both collections. SLAP-2M cameras of a session have identical frame counts. The per-camera timestamps in SLAP-2M file names differ by 6 to 18 s within a session, which reads as file creation order.
- **Current handling:** `StartTime: 0` everywhere, with the source timestamp kept in each sidecar's `Synchronization` block.
- **Ask the lab:** were the SLAP-2M cameras hardware-triggered, so that frame N is simultaneous across cameras?

### Q8. Three stray analysis files

SLAP-2M sessions `10212022175626` (top, topL) and `10212022181154` (back) each hold a `*.predictions.proofread.slpanalysis.h5` beside the regular `*.predictions.proofread.slp.analysis.h5`.

- **Current handling:** reported in the run summary and not converted.

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
| Q4 | One derivative dataset or several | One, `derivatives/pipeline-luc3d/` | Request 4 |
| Q5 | Models | Kept, in `derivatives/pipeline-luc3d/models/` | Requests 2 and 4 |
| Q7 | Lab key | `talmo` | Request 2 |
| Q13 | Derivative dataset names and where the models sit | Everything under `derivatives/pipeline-luc3d/` | Request 4 |
