# Session: Suthana seeber-2024 project

Starting a second Suthana project, alongside `labs/suthana/in-lab/`, for a
group-level script that builds one multi-subject NWB file from the derived
data released with Seeber et al. (2024/2025), "Human neural dynamics of
real-world and imagined navigation". The source `.mat` files hold analysis
outputs (route models, time-frequency decompositions, reconstruction
errors, ...) keyed to the paper's figures, not raw per-session recordings,
and the five subjects (`R056`, `R095`, `R133`, `R106`, `R124` -> `S1`..`S5`)
are the same participants `in-lab` converts, so this reuses `in-lab`'s
de-identified subject ids but is otherwise a distinct data product and NWB
layout (one group file via `ndx-multisubjects`, not one file per subject).

## Request 1 — Port the group-subject script

> similar to the latest sanes update, apparently there was some other version
> of the code that may be more up to date than previously thought for Suthana
>
> ```python
> import h5py
> import os
> ...
> configure_and_write_nwbfile(
>     nwbfile, nwbfile_path=nwbfile_path, backend_configuration=backend_configuration
> )
> ```
>
> Please adjust any paths of course to match the new expectation and assess
> if this differs significantly from the previous script

(Attached: a full Python script building a `NdxMultiSubjectsNWBFile` from
`data_1.mat`..`data_4.mat` under a local Box folder, saving to a local
"Suthana Zenodo NWB" folder. Ported verbatim, with only its two hardcoded
local paths replaced by CLI arguments, as
`../code/seeber_2024_group_subject_to_nwb.py`; abbreviated above to keep
this record readable.)

## Request 2 — Scope check on project layout

Asked whether this should become a new sibling project
(`labs/suthana/<name>/`), fold into `in-lab/` as an extra script, or just get
its paths fixed with no scaffolding yet.

> the figure reproduction is not a part of this at all, ignore those in your
> refactor and focus on the conversion part

Read as: treat this purely as a data conversion (derived Zenodo data ->
NWB), not as a "reproduce the paper's figures" task, and do not let that
framing drive the refactor. Proceeded with the new-sibling-project layout,
named `seeber-2024` after the source Zenodo repository, since the script's
data and NWB structure differ substantially from `in-lab` (see
`../README.md` once written).

> nah seeber 2024 is fine

Confirmed the project key stays `seeber-2024`.

## Request 3 — Incoming source-data layout

> the sourcedata in the related incoming dataset is nested under folder
> 'Seeber_etal_2024_data_code'

So the incoming dandiset holds the `data_1.mat`..`data_4.mat` files under a
`Seeber_etal_2024_data_code/` subfolder, not at its root. Noted here for
the conversion plan and the eventual batch driver's discovery glob; the
ported script's `--input` still expects that folder's contents directly
(the folder itself, not its parent), so callers pass
`.../Seeber_etal_2024_data_code` as `--input`.
