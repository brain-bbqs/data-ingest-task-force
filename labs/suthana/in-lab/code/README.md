<!-- Original conversion notes written by Neha Thomas, ported from the
original conversion work (Suthana_inLab_DataConversion.py /
Suthana_MATdata_full.ipynb). The "Original notes" section below is unchanged.
Everything under "Input data layout" was written during the port, reading it
off the conversion script, because the original notes left those headings
empty. See ../README.md for how the project is wired into this repository. -->

## Original notes

### Overview


### Data Organization


### Variable Names:


### Folder and File Structure
```
sub-XYZ/
└── ses-YYYYMMDD/
    └──  sub-XYZ_ses-YYYYMMDD.nwb
        ├── session_start_time
        ├── session_description
        ├── identifier
        ├── general
        │   └── subject
        ├── acquisition
        │   └── TimeSeries
        └── processed
            └── TimeSeries
```

## Input data layout

This is the data conversion from the Suthana team (R61MH135106). Participants
with chronically implanted medial temporal lobe electrodes navigated two
learned routes in an indoor room, first walking them and later imagining them,
while motion capture, eye tracking, scalp EEG and iEEG were recorded together.
See the paper for the full protocol: https://doi.org/10.1038/s41562-025-02119-3

One `.mat` file holds one subject's whole experiment. The recording is split
into several non-contiguous segments, and every modality is stored per segment.

```
incoming/
├── <subject>_aligned_data.mat ... (one per subject)
└── Trajectories_runtimes.csv     (one column per subject, one row per segment)
```

The files are MATLAB v7.3, which is HDF5, so they are read with `h5py`
directly. MATLAB cell arrays appear as arrays of HDF5 object references into a
`#refs#` group, and char arrays as arrays of UTF-16 code units. Both have to be
dereferenced and decoded by hand.

Inside one `.mat` file:

```
Trajectories/
├── Fs                            sampling rate, shared by every modality
├── Subject_ID                    raw subject id, e.g. R056
└── recordings/                   each entry is (n_segments, 1) cell of refs
    ├── gaze                      → (2, n_samples) gaze x/y in pixels
    ├── head_rotation             → data (3, n_samples) + hdr column labels
    ├── position                  → data (10, n_samples) + hdr column labels
    ├── iEEG                      → data (4, n_samples) + ix_IED artifact mask
    ├── scalp_EEG                 → data (63, n_samples) + ix_art + chan_labels
    └── events                    → beep (2, n) and button (5, n) cells
```

The 10 rows of `position` are the tracked body-part centroids, in order: hip
(2 rows), left leg (3), right leg (3), head (2).

Event cells carry a 1-based sample index into the segment, which the conversion
turns into a session-relative time in seconds.

`Trajectories_runtimes.csv` gives each segment's wall-clock start time. The
column whose header contains the subject's de-identified paper id (S1..S5) is
that subject's. The first segment's start becomes the session start time, and
every other segment is positioned relative to it.

### Folder and file structure produced

```
sub-<paper id>/
└── sub-<paper id>_ses-inlab_behavior+ecephys.nwb
    ├── session_start_time
    ├── session_description
    ├── identifier
    ├── general
    │   ├── subject
    │   ├── devices (iEEG array, scalp EEG array)
    │   └── extracellular_ephys (electrodes: 4 iEEG + 63 scalp EEG)
    └── processing
        ├── behavior
        │   ├── HeadRotation_All      ← head_rotation (CompassDirection)
        │   ├── EyeTracking_All       ← gaze (EyeTracking)
        │   ├── Pose_Hip_All          ← position rows 0-1 (Position)
        │   ├── Pose_LeftLeg_All      ← position rows 2-4 (Position)
        │   ├── Pose_RightLeg_All     ← position rows 5-7 (Position)
        │   ├── Pose_Head_All         ← position rows 8-9 (Position)
        │   ├── beep_events           ← events.beep (DynamicTable)
        │   └── button_events         ← events.button (DynamicTable)
        ├── iEEG
        │   ├── Processed iEEG Segment NN        (ElectricalSeries)
        │   └── iEEG Artifact Series Segment NN  ← ix_IED (TimeSeries)
        └── scalp EEG
            ├── Processed scalp EEG Segment NN        (ElectricalSeries)
            └── scalp EEG Artifact Series Segment NN  ← ix_art (TimeSeries)
```

Each segment contributes its own series to every container, named
`... Segment NN` and positioned by a `starting_time` measured in seconds from
the session start. Assets sit directly under `sub-<paper id>/` rather than in a
`ses-` subfolder, because dandi validation rejects nested session folders.

### Notes

`_suthana_in_lab_to_nwb.py` converts one subject's `.mat` file into one NWB
file. The wrapper `batch_convert.py` calls it for every `.mat` file found under
an incoming directory and creates the subject layout above. This is the entry
point dispatch runs (see `dispatch/projects.json`).
