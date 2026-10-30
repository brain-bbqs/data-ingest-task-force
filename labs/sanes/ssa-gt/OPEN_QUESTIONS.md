# Open questions

| ID | Status | Question |
|---|---|---|
| Q1 | Deferred | Replace provisional animal sex, age, experimenter, timezone, and device metadata. A `PROVISIONAL` age fails DANDI's `check_subject_age`. |
| Q2 | Resolved | Per-animal NWB files are emitted next to the multisubject file (Request 16), each in its own `sub-<NN>/` folder so the DANDI layout validates. |
| Q3 | Resolved | The concatenated standardized video is referenced externally; source chunk videos are not referenced. |
| Q4 | Resolved provisionally | Experiment logs now provide the first `Started Experiment Now` timestamp. Confirm that logged times are UTC. |
| Q5 | Resolved provisionally | Experiment metadata is structured in `code/experiment_metadata.yaml`; confirm animal IDs and metadata for experiments not covered by the supplied document. |
| Q6 | Open | The BIG_ARENA_2024_12 (`000601`) and BIG_ARENA_2025_03 (`000602`) layouts were not inspected before registration. Confirm they match SSA GT: `experiment_*` folders under `sourcedata/raw/` or one folder below it, `idx_*` chunks with per-channel WAVs, one MP4, tracks and annotation CSVs, and an experiment log. Supply per-experiment metadata if it exists. |
| Q7 | Open | Only nose x/y is stored. Should every landmark and confidence score be stored, for example with `ndx-pose`? |
| Q8 | Open | `sub-<NN>` comes from track order, so the same label recurs across experiments for different animals. Can tracks be mapped to animal IDs (such as `35-neck` and `118-fluffy`)? |

The current converter keeps the approved `ses-experiment<ID>` labels and direct root DANDI layout.
