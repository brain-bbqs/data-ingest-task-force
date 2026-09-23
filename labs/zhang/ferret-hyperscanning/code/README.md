# Conversion notes

What `_zhang_ferret_hyperscanning_to_nwb.py` does, the source-to-output
mapping it implements, and the naming decisions behind it. The intake and
the reviewed plan live in `../prompts/initial.md`.

## What the converter does

One recording is one SpikeGadgets `.rec` directory. It holds a Trodes file of
the same name with both animals' headstages, and shares a sibling `Videos/`
directory with any other recording made on the same day. The converter
writes two NWB files per recording, one per animal, and places the
session's videos next to the lower-numbered animal's file so both files can
reference them by relative path.

Each file is assembled by a NeuroConv `ConverterPipe`. The ephys goes
through `SpikeGadgetsRecordingInterface`, which reads the `trodes` stream
through spikeinterface and neo and builds the device, electrode groups and
electrode table; each animal's file takes only that headstage's channels.
Each video goes through its own `ExternalVideoInterface`, which reads the
frame rate and frame count from the file header and links the camera
device. That interface stores the absolute path it read the file from, so
the converter rewrites each `external_file` to be relative to the NWB file
before writing, which is what DANDI resolves after upload.

## Input layout

```
<incoming>/sourcedata/raw/Ferret_Hyperscanning/
  <pair>/                         e.g. 0236-0237
    <MM.DD.YYYY>/                 e.g. 04.01.2026
      <A>HS<n>_<B>HS<m>_<YYYYMMDD>_<HHMMSS>.rec/
        <same name>.rec           Trodes recording, both headstages
      Videos/
        cam<NN>-<MMDDYYYYHHMMSS>-0000.avi        behavior video, one per camera
        cam<NN>-cal-<MMDDYYYYHHMMSS>-0000.avi    ChArUco calibration video, one per camera
```

## Mapping

| Source | Output |
| --- | --- |
| `<rec>.rec/` directory | One session, two files: `sub-0236/sub-0236_ses-20260401T130419_behavior+ecephys.nwb` and `sub-0237/sub-0237_ses-20260401T130419_behavior+ecephys.nwb` |
| `.rec` XML header | `session_start_time` from `systemTimeAtCreation` in the configured timezone (falls back to the basename's timestamp), sampling rate, per-channel gain |
| `.rec` ephys packets | `acquisition/ElectricalSeries`, this animal's 32 channels only, int16 with the header's `spikeScalingToUv` as `conversion` |
| `.rec` digital inputs and headstage sensor block | Not read yet. Frame-pulse sync and the accelerometer are follow-ups |
| `<rec>.trodesComments` | Not read yet. Human-interference intervals are a follow-up once the lab says where the comments live |
| `Videos/cam<NN>-<ts>-0000.avi` | `acquisition/BehaviorVideoCam<NN>` via NeuroConv's `ExternalVideoInterface` (external `ImageSeries`, rate and frame count from the file header, `starting_time` 0.0 PROVISIONAL), file placed as `sub-<host>/sub-<host>_ses-<label>_cam<NN>_video.avi` |
| `Videos/cam<NN>-cal-<ts>-0000.avi` | `acquisition/CalibrationVideoCam<NN>` (same shape), file placed as `..._cam<NN>_calibration.avi` |
| `session_log.csv` row (pair and date, nearest start time) | Belly-up flag selects the channel map; usable-data text and notes land in `notes` |
| `config.yaml` | Everything else: lab, institution, subjects, devices, regions, channel maps, video rate |
| Anything else in a session | Reported and left alone |

## Output structure

```
<standardized>/
  sub-0236/
    sub-0236_ses-20260401T130419_behavior+ecephys.nwb
    sub-0236_ses-20260401T130419_cam14_video.avi
    sub-0236_ses-20260401T130419_cam14_calibration.avi
    ... (cam46, cam58, cam67, cam68 likewise)
  sub-0237/
    sub-0237_ses-20260401T130419_behavior+ecephys.nwb
      (its ImageSeries point at ../sub-0236/...)
```

Each NWB file:

```
session_start_time         from the Trodes header, timezone PROVISIONAL
session_description        "Ferret hyperscanning, subject 0236 (headstage HS3) with partner 0237 (HS4): ..."
session_id                 20260401T130419
identifier                 zhang-ferret-hyperscanning-20260401T130419-sub-0236
general/
  subject                  subject_id, species, sex (PROVISIONAL), age (PROVISIONAL), identification mark
  lab, institution (PROVISIONAL), experimenter (PROVISIONAL), experiment_description, keywords, notes
  devices/                 Sprite32HS<n>, BlackflyS_cam<NN> x5
  extracellular_ephys/
    electrode_groups/      PMC (premotor cortex), PPC (posterior parietal cortex)
    electrodes             32 rows: group_name, location, channel_name, headstage_channel, reference_electrode
acquisition/
  ElectricalSeries         N x 32 int16 at 20 kHz
  BehaviorVideoCam<NN>     ImageSeries, external, x5
  CalibrationVideoCam<NN>  ImageSeries, external, x5
```

Videos are hard-linked into the standardized tree when it shares a
filesystem with the incoming tree, copied otherwise.

## Naming decisions

Each lives in one function of `_zhang_ferret_hyperscanning_to_nwb.py`:

- **Session label** (`derive_session_label`): the basename's date and time
  joined as `20260401T130419`.
- **Subject labels** (`derive_subject_labels`): the two four-digit ids from
  `<A>HS<n>_<B>HS<m>`, in basename order, checked against the pair
  directory by `parse_rec_identity`.
- **Channel split** (`headstage_channel_ids`): the first headstage in the
  basename takes hardware channels 0 to 31, the second 32 to 63.
  PROVISIONAL until a real file's `SpikeConfiguration` confirms it.
- **Channel map** (`select_channel_map`): odd channels are PMC and even
  channels PPC when belly-down, swapped when the session log flags belly-up.
  Channels 30 and 31 are the reference electrodes.
- **Video matching** (`match_videos`): per camera and kind, the file whose
  timestamp is nearest the recording's.
- **Host subject** (`RecordingIdentity.host_subject`): the lower animal id
  holds the shared video files.

## Running it by hand

```bash
python3 labs/zhang/ferret-hyperscanning/code/_zhang_ferret_hyperscanning_to_nwb.py \
    --input path/to/0236HS3_0237HS4_20260401_130419.rec \
    --output path/to/standardized/000547 \
    --config labs/zhang/ferret-hyperscanning/code/config.yaml
```

`batch_convert.py` runs this over every recording under an incoming
dandiset. It converts two recordings at a time by default (`--jobs`): memory
is not the constraint, but each recording moves about 170 GB of video.
