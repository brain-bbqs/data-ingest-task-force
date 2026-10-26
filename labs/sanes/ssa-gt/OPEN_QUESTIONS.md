# Open questions

| ID | Status | Question |
|---|---|---|
| Q1 | Deferred | Replace provisional animal sex, age, experimenter, timezone, and device metadata. |
| Q2 | Deferred | Confirm animal metadata and whether separate per-animal NWB assets should also be emitted. The session now uses `ndx-multisubjects.SubjectsTable`. |
| Q3 | Resolved | The concatenated standardized video is referenced externally; source chunk videos are not referenced. |
| Q4 | Resolved provisionally | Experiment logs now provide the first `Started Experiment Now` timestamp. Confirm that logged times are UTC. |
| Q5 | Resolved provisionally | Experiment metadata is structured in `code/experiment_metadata.yaml`; confirm animal IDs and metadata for experiments not covered by the supplied document. |

The current converter keeps the approved `ses-experiment<ID>` labels and direct root DANDI layout.
