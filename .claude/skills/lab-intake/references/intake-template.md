# Intake record template

Fill in what the description answers. Leave unknowns open rather than guessing. Mark unconfirmed working values `PROVISIONAL` with a note of what would confirm them.

## Identity

| Field | Value |
| --- | --- |
| Lab key (lowercase PI surname, the `labs/` directory name) | |
| Project name (only for a lab with more than one distinct data collection) | |
| PI and lab | |
| Institution | |
| Grant award number (e.g. `R34DA059514`, used in image and package names) | |
| Contact for metadata questions | |

## Registration targets

| Field | Value |
| --- | --- |
| Incoming dandiset id (six digits, holds the raw uploads) | |
| Standardized dandiset id (six digits, receives the output; may equal incoming) | |
| DANDI instance (default `ember-dandi`, browse at `https://dandi.emberarchive.org/dandiset/<id>`) | |

## The science

| Field | Value |
| --- | --- |
| Species (Latin binomial, e.g. `Ovis aries`, `Homo sapiens`) | |
| Task or behavior being recorded | |
| Data modalities (video, audio, ephys/iEEG/EEG, pose, IMU, eye tracking, ...) | |
| Acquisition systems and devices (cameras, probes, implants, software) | |

## Associated papers

DOIs or links, one per line. These become `related_publications` in NWB metadata or dataset-level references in BIDS, and they are often the best source for device and protocol details the description leaves out.

## Source data

- Verbatim file tree of at least one representative session (pasted `tree` output, unedited):

  ```
  <paste>
  ```

- What each file is, per extension or name, including files that should be ignored.
- File formats and rough sizes. This matters later for memory and parallelism choices.
- How sessions appear in the tree. This becomes the project's `sessions.json` include glob, and only directories count as sessions.
- How subject and session identity are encoded (folder names, filenames, a spreadsheet, nowhere yet).

## Metadata provided

- Subject-level: id, species, sex (DANDI requires one of `M`/`F`/`O`/`U`), and age as an ISO 8601 duration (e.g. `P30Y`, `P5W3D`) or a date of birth.
- Session-level: start time with timezone, description, experimenters.
- Device, electrode group, and channel-map details where applicable (names, locations, coordinates, filtering).
- Anything else supplied (protocol, surgery notes, pharmacology, virus, keywords).

## Target standard

| Field | Value |
| --- | --- |
| Standard named by the requester (NWB, BIDS BEP047, or none named) | |
| Spec references supplied (BEP links, example datasets, `ndx-*` extensions) | |
| Example of the expected output supplied (tree, file, or link) | |

## Prior conversion work

| Field | Value |
| --- | --- |
| Existing scripts or notebooks (attached or linked) | |
| Original author(s), for credit | |
| Port mode (verbatim as provenance, or improve on the way in) | |

## Operational

| Field | Value |
| --- | --- |
| Expected session count and total data volume | |
| Anything memory- or compute-heavy (whole-video decodes, 50 kHz analog, ...) | |
| Runtime dependencies beyond Python packages (FFmpeg, MATLAB readers, ...) | |

## Minimum to proceed to a conversion plan

- [ ] Lab key settled, and the flat-vs-project layout question answered
- [ ] At least one verbatim session tree, with the meaning of each file
- [ ] Modalities and acquisition systems understood
- [ ] Species known
- [ ] Target standard named, or enough of the above to propose one
- [ ] Prior-work question answered (none, or scripts in hand with authors known)

Dandiset ids, papers, complete metadata, and an expected-output example are all deferrable, carried as `PROVISIONAL` values or open questions.
