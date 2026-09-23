# Session: Zhang lab intake and conversion plan

Setting up the Zhang lab (Michigan State University, R34DA061924) conversion of
ferret hyperscanning recordings, working through the new-conversion skills in
order: lab-intake, then lab-conversion-plan, stopping for the requester's review
of the plan before lab-scaffold and lab-register run. Incoming dandiset
`000480`, standardized output `000547`.

## Request 1 — Set up the conversion

> Please set up a new conversion for the Zhang lab, working through the
> new-conversion skills in .agents/skills/ in order: lab-intake, then
> lab-conversion-plan, then stop for my review of the plan before running
> lab-scaffold and lab-register. Finish with lab-lessons, encoding anything
> this conversion taught back into the skills.
>
> \- Lab / PI: Mengsen Zhang,  Michigan State University
> \- Grant award number: R34DA061924
> \- Project name: Mapping dynamic transitions across neural, behavioral, and social scales in ferrets and humans
> \- Incoming dandiset: [https://dandi.emberarchive.org/dandiset/000480](https://dandi.emberarchive.org/dandiset/000480)
> \- Standardized output dandiset: [https://dandi.emberarchive.org/dandiset/000547](https://dandi.emberarchive.org/dandiset/000547)
> \- Data standard: propose options for my decision
> \- Associated papers:  "none"
> \- Source data tree:
>
> ```
> sourcedata/
> └── raw/
>     └── Ferret_Hyperscanning/
>         └── 0236-0237/
>             ├── 03.20.2026/
>             ├── 03.24.2026/
>             ├── 03.26.2026/
>             ├── 03.27.2026/
>             ├── 03.31.2026/
>             └── 04.01.2026/
>                 ├── 0236HS3_0237HS4_20260401_130419.rec/
>                 │   └── 0236HS3_0237HS4_20260401_130419.rec     764.39 MB
>                 └── Videos/
>                     ├── cam14-04012026122439-0000.avi           29.47 GB
>                     ├── cam14-cal-04012026121856-0000.avi        4.69 GB
>                     ├── cam46-04012026122433-0000.avi           29.47 GB
>                     ├── cam46-cal-04012026121851-0000.avi        4.69 GB
>                     ├── cam58-04012026122436-0000.avi           29.47 GB
>                     ├── cam58-cal-04012026121853-0000.avi        4.69 GB
>                     ├── cam67-04012026122443-0000.avi           29.47 GB
>                     ├── cam67-cal-04012026121854-0000.avi        4.69 GB
>                     ├── cam68-04012026122430-0000.avi           29.47 GB
>                     └── cam68-cal-04012026121850-0000.avi        4.69 GB
> ```
>
> \- Metadata: please see added context (metadata form and spreadsheet)
> \- Expected output example: "draft one for my review"
> \- Prior conversion code: "none"

(Attached: the BRAIN-BBQS data-intake questionnaire response as a PDF, and
`Ferret_Hyperscanning_MetaData.xlsx`, the lab's session log and metadata
spreadsheet, both uploaded with the request.)

### Intake summary

Filled from the request, the questionnaire and the spreadsheet. The ember
archive API is not reachable from the sandbox this ran in (proxy 403), so the
dandiset was not inspected and the tree above is the only view of the data.

- **Lab / PI / grant:** Zhang lab, Mengsen Zhang, Michigan State University,
  `R34DA061924`. The questionnaire contact is at UNC School of Medicine
  (gabriella_sahyoun@med.unc.edu), so the recording site may differ from the
  PI's institution.
- **Dandisets:** incoming `000480`, standardized `000547`, instance
  `ember-dandi`.
- **Species:** *Mustela putorius furo*. Three animals, `0235`, `0236`, `0237`,
  recorded as dyads (`0235-0236`, `0235-0237`, `0236-0237`).
- **Experiment (questionnaire):** "Simultaneous wireless electrophysiology
  recordings of ferret dyads during naturalistic behavior in an open field box
  with a toy included. Electrophysiology is recorded from two cortical regions,
  the premotor cortex and the posterior parietal cortex. Behavior is recorded
  from five camera angles."
- **Streams and devices:** 32-channel extracellular ephys per animal at 20 kHz
  from SpikeGadgets Sprite32 wireless datalogger headstages via Trodes; head
  acceleration from the same headstage; five Teledyne FLIR Blackfly S USB3
  cameras at 30 fps, hardware-triggered together, with one digital input pulse
  per frame recorded by the ephys system; Trodes comments `hi` / `ho` marking
  human interference; a ChArUco calibration video per camera before each
  session.
- **Channel map (spreadsheet):** belly-down, odd channels 1 to 31 are PMC
  (31 is the PMC reference, 0.5 mm above the rest) and even channels 0 to 30
  are PPC (30 is the PPC reference). Belly-up (the spreadsheet's
  `Headstage Belly Up` flag, 1 from the 2026-04-14 afternoon session onward)
  swaps the two regions.
- **Session log (spreadsheet):** 109 rows, date, pair, start and end wall
  clock time, usable-data duration as free text, the belly-up flag, and an
  empty notes column. Twelve date-pair combinations have two rows. The tree
  shows six of the 31 logged dates for `0236-0237` and no `0235-*` pair, so
  the upload is partial or in progress.
- **Not provided:** sex, age or date of birth, experimenters, timezone,
  electrode type and coordinates, which digital input carries the frame trigger, where
  the Trodes comments live, standard, papers, prior code.

Size arithmetic that shapes the plan: at 30 fps, a 29.47 GB video is 20.8
minutes of uncompressed 1024x768 8-bit frames, matching the session's
"21min" usable-data entry. Over 20.8 minutes at 20 kHz the `.rec` holds about
25 million packets, so 764 MB is about 31 bytes per packet, while 64 int16
ephys channels alone need 128. The uploaded `.rec` therefore cannot hold both
headstages' full-rate ephys. It reads like the base-station recording (sync,
digital inputs, timestamps), with the datalogger SD-card data not yet merged
in or not uploaded. That is open question 1.

## Conversion plan (draft for review)

Written for the agent that will scaffold `labs/zhang/`. Every decision marked
**requester decides** is awaiting sign-off; everything else is a proposed
default that is easy to change. The precedents referenced are
`labs/inman/` (per-subject NWB files, `config.yaml` pattern),
`labs/sanes/` (multi-animal sessions via `ndx-multisubjects`) and
`labs/kemere/` (BEP047 video handling).

### Open questions, in priority order

(As asked at plan time. Their current status is tracked in
[`../OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md), under the same numbers.)

1. **Does the uploaded `.rec` contain the ephys?** By size it cannot hold
   64 channels at 20 kHz for the session. Is it the base-station file, with
   the Sprite32 SD-card data merged into a separate (larger) `.rec` through
   Trodes' datalogger merge, or exported some other way? Where are those files
   and how are they named? The plan below assumes a merged `.rec` holding both
   headstages; if the ephys lives elsewhere, the ephys rows of the mapping
   table move to that file and the `.rec` in the tree becomes the sync source
   only.
2. **Layout, requester decides:** flat `labs/zhang/` or nested
   `labs/zhang/ferret-hyperscanning/` (project key
   `zhang/ferret-hyperscanning`, image
   `ghcr.io/brain-bbqs/zhang-ferret-hyperscanning-r34da061924-ingest`).
   Recommended: nested, because the dataset title covers ferrets *and*
   humans and the raw tree already nests under `Ferret_Hyperscanning/`.
   Renaming later means churn across dispatch and CI.
3. **Standard, requester decides:** option A, B or C below. Recommended: A.
4. **Video handling, requester decides:** carry the raw AVIs into the
   standardized dandiset unchanged (about 172 GB per session, roughly 19 TB
   for the logged sessions), transcode on the way in (lossless FFV1 in MKV,
   or H.264 at a visually lossless CRF, each a lab call on acceptability for
   pose estimation), or keep the videos only in `000480` and reference
   nothing from the NWB. Recommended: unchanged AVIs as external files, with
   transcoding as the fallback if the volume is unacceptable.
5. **Clocks.** The behavior videos are stamped 12:24 and the calibration
   videos 12:18, while the `.rec` is stamped 13:04 and the spreadsheet says
   1:14 PM to 1:42 PM. Is the camera computer's clock offset, or are these
   different recordings? The plan aligns video to ephys through the frame
   pulses, so this only matters for placing the calibration videos and for
   sanity checks, but it needs an answer.
6. **Where are the Trodes comments?** Trodes writes `<rec>.trodesComments`
   next to the `.rec`; nothing like it is in the tree. If they were not
   uploaded, the human-interference intervals cannot be built.
7. **Which digital input carries the camera frame trigger,** and is every camera's
   first frame the first pulse? The converter will pick the digital channel
   with a pulse rate near 30 Hz and report the pulse count against each
   video's frame count, but the channel id should be confirmed.
8. **Channel numbering per headstage.** Does the odd/even 0 to 31 map apply
   to each animal's 32 channels separately, and how does the `.rec` header
   identify which nTrodes belong to `HS3` versus `HS4`?
9. **Subject and session metadata:** sex, age or date of birth, weight,
   experimenter names, institution of data collection, timezone.
10. **Electrodes:** type and geometry, coordinates, impedances, the
    filtering applied, and whether channels 30 and 31 are recorded channels
    used as software references or hardware reference inputs.
11. **Accelerometer:** units or scale factor, and the real sample rate (the
    questionnaire says 20 kHz; SpikeGadgets headstage sensors are usually
    interleaved at a much lower rate).
12. **Spreadsheet as a runtime input.** The session log is the only source of
    the belly-up flag and usable-data notes. Proposed: commit a CSV export of
    both sheets under `code/` (`session_log.csv`, and the rest folded into
    `config.yaml`) and have the lab send updates by PR. Alternative: upload
    the spreadsheet to a fixed path in `000480` and read it from there. Also
    the `4/23/206` date typo and the AM/PM-less times in later rows need the
    lab's confirmation of the parsing rule (times after 8:00 without AM/PM
    are PM).
13. **Two recordings on one date.** Twelve date-pair combinations have two
    spreadsheet rows. Do those days hold two `.rec` directories sharing one
    `Videos/` folder? The plan matches each `.rec` to the video set whose
    filename timestamp is nearest, but that rule needs a real example.
14. **Sessions to exclude.** 29 rows have no usable-data value. Should those
    still be converted, and should anything be excluded outright?
15. **Calibration videos.** Include them in the NWB as `ImageSeries` placed
    on the session clock (they start before the recording, so with a
    negative `starting_time`), or copy them into the standardized tree as
    plain assets without an NWB reference? Proposed: in the NWB.

### Step 1: Standard and granularity

No standard was named. The decision guide in
`.agents/skills/lab-conversion-plan/references/standards.md` points at NWB
for neural recordings with behavior, and the only precedent for
several animals in one session is sanes. Three workable options:

**Option A (recommended): NWB, one file per subject per session.** Each
ferret gets its own NWB file holding its 32-channel `ElectricalSeries`, its
head acceleration, the shared frame-trigger events, the human-interference
intervals, and the five behavior videos plus five calibration videos as
external-file `ImageSeries`. The partner animal is named in the session
description and in `notes`. This is DANDI's native layout (`sub-<id>/`,
one `Subject` per file), validates with the default `upload_validation`,
and every NWB tool understands it. Cost: the shared streams (frame times,
intervals, video references) appear in both files, and a hyperscanning
analysis opens two files per session. A session-level file linking the
pair through `ndx-multisubjects` can be added later without redoing the
ephys, since that extension links to exactly these per-subject files (the
sanes v2 pattern).

**Option B: NWB, one file per dyad session with `ndx-multisubjects`.** Both
animals' `ElectricalSeries` in one file with a two-row `SubjectsTable`
(sanes precedent). One time base, no duplication, the natural unit for
dyadic analysis. Cost: no core `Subject`, so DANDI's subject metadata
extraction and `sub-<id>/` layout need a synthetic dyad label or
`upload_validation: ignore` as sanes uses, and most NWB tooling (inspector,
viewers) does not yet handle multi-subject files.

**Option C: split standards.** NWB per subject for the ephys (as A) and a
BEP047 BIDS `beh` tree for the raw videos (kemere precedent). Not
recommended: one session would straddle two standards and the video-to-ephys
sync would have to be expressed twice.

Granularity under option A: two files per session, one per animal, named
`sub-<animal>_ses-<label>_behavior+ecephys.nwb` (inman's stream suffix
convention). **Requester decides** on both the option and the granularity.

### Step 2: Mapping every source file

Session unit: one `.rec` directory. Dispatch include glob
`sourcedata/raw/Ferret_Hyperscanning/*/*/*.rec` (only directories match,
so it selects the `.rec` directory, whose basename is unique across pairs;
the date directories are not, and dispatch keys sessions by basename).

| Source | Output |
| --- | --- |
| `Ferret_Hyperscanning/<pair>/<MM.DD.YYYY>/<rec>.rec/` | One session: `sub-0236/sub-0236_ses-20260401T130419_behavior+ecephys.nwb` and `sub-0237/sub-0237_ses-20260401T130419_behavior+ecephys.nwb` |
| `<rec>.rec/<rec>.rec`, XML header | `session_start_time` (from `systemTimeAtCreation`, timezone `PROVISIONAL`), sampling rate, per-channel gain (`spikeScalingToUv`), nTrode-to-headstage assignment, `Device` entries |
| `<rec>.rec/<rec>.rec`, ephys packets | `acquisition/ElectricalSeries`, this animal's 32 channels only, int16 with `conversion` from the header gain, timestamps from the Trodes clock (rate + starting time when the clock is continuous, explicit timestamps if the packet timestamps show gaps) |
| `<rec>.rec/<rec>.rec`, digital inputs | Rising-edge times of the camera frame digital input become the `timestamps` of every behavior-video `ImageSeries`; the digital input's state changes are also kept as `processing/behavior/BehavioralEvents/camera_frame_trigger` (`TimeSeries`, 0/1 at transitions) |
| `<rec>.rec/<rec>.rec`, headstage sensor block | `acquisition/HeadstageAccelerometer` (`TimeSeries`, x/y/z, unit and rate `PROVISIONAL`) |
| `<rec>.trodesComments` (expected next to the `.rec`, not in the tree) | `intervals/human_interference` (`TimeIntervals`, start at `hi`, stop at `ho`, unpaired comments reported); skipped with a report when the file is absent |
| `Videos/cam<NN>-<ts>-0000.avi` | `acquisition/BehaviorVideoCam<NN>` (`ImageSeries`, `format="external"`, relative `external_file`, timestamps from the frame digital input, `description` naming the camera and the original filename); the file itself is placed under the host subject's directory (see Step 3) |
| `Videos/cam<NN>-cal-<ts>-0000.avi` | `acquisition/CalibrationVideoCam<NN>` (`ImageSeries`, external, `rate=30.0`, `starting_time` derived from the filename offset to the behavior video and the first frame pulse, `description` noting the ChArUco board) |
| Spreadsheet `Session Info` row (matched by pair and date, nearest start time when two rows share a date) | Belly-up flag selects the channel map; usable-data text and notes go to `notes`; start and end times are cross-checked against the `.rec` and reported |
| Spreadsheet `Other Meta Data` | Channel maps, animal identification marks, comment legend, and rates land in `config.yaml` at scaffold time |
| Questionnaire | `experiment_description`, `keywords`, device names and rates in `config.yaml` |
| Anything else under a session | Out of scope, reported and left alone |

Identity rules, each to live in one function once in code:

- `derive_subject_labels(rec_name)`: the two four-digit ids from
  `<A>HS<n>_<B>HS<m>_...`, checked against the pair directory name
  (`0236-0237`); the headstage ids ride along for device naming. Mismatch
  is an error, not a guess.
- `derive_session_label(rec_name)`: `YYYYMMDD` and `HHMMSS` from the
  basename joined as `20260401T130419`. Alphanumeric, unique per recording,
  and sortable.
- `select_channel_map(belly_up)`: the two maps from the spreadsheet, keyed
  by the flag; the belly-down map is the default when a session has no
  spreadsheet row, with a report.
- `match_videos(rec_dir)`: the five `cam<NN>-<ts>` behavior videos and five
  `cam<NN>-cal-<ts>` calibration videos in the sibling `Videos/` directory
  whose timestamps are nearest the `.rec` timestamp; fewer than five of
  either is reported, and a session with no behavior video is still
  converted (ephys only) with a report.
- `derive_host_subject(subject_labels)`: the lower animal id hosts the
  shared video files; the partner's NWB references them with a
  `../sub-<host>/` relative path.

### Step 3: Expected output example

One session, under option A:

```
000547/
  sub-0236/
    sub-0236_ses-20260401T130419_behavior+ecephys.nwb
    sub-0236_ses-20260401T130419_cam14_video.avi
    sub-0236_ses-20260401T130419_cam14_calibration.avi
    sub-0236_ses-20260401T130419_cam46_video.avi
    sub-0236_ses-20260401T130419_cam46_calibration.avi
    ... (cam58, cam67, cam68 likewise)
  sub-0237/
    sub-0237_ses-20260401T130419_behavior+ecephys.nwb
      (its ImageSeries point at ../sub-0236/sub-0236_ses-..._cam<NN>_*.avi)
```

Videos are hard-linked when incoming and standardized share a filesystem,
copied otherwise. Whether DANDI accepts `.avi` assets next to NWB files
under `sub-<id>/` with the default upload validation has to be confirmed
on the first real run; kemere's BIDS tree is the only precedent for
non-NWB assets and it lives under `sourcedata/`.

Internal structure of `sub-0236_ses-20260401T130419_behavior+ecephys.nwb`:

```
session_start_time         2026-04-01T13:04:19-04:00 (Trodes header; tz PROVISIONAL)
session_description        "Ferret hyperscanning, subject 0236 (headstage HS3) with
                            partner 0237 (HS4): naturalistic behavior of the dyad in an
                            open-field box with a toy. Belly-down channel map."
identifier                 uuid4
general/
  subject                  subject_id 0236, species Mustela putorius furo,
                           sex U (PROVISIONAL), age (PROVISIONAL),
                           description "no shave" (identification mark)
  lab                      Zhang Lab
  institution              Michigan State University (PROVISIONAL)
  experimenter             (PROVISIONAL)
  experiment_description   questionnaire text
  keywords                 hyperscanning, ferret, social behavior, premotor cortex,
                           posterior parietal cortex, wireless electrophysiology
  notes                    spreadsheet row: usable data ~21min, partner 0237, pair 0236-0237
  devices/
    Sprite32HS3            SpikeGadgets Sprite32 wireless datalogger headstage, Trodes
    BlackflyS_cam14 ...    Teledyne FLIR Blackfly S USB3 (one per camera)
  extracellular_ephys/
    electrode_groups/
      PMC                  location "premotor cortex", device Sprite32HS3
      PPC                  location "posterior parietal cortex", device Sprite32HS3
    electrodes             32 rows: channel_name (hwChan), group, location,
                           reference_electrode (True for 30 and 31), notes on the
                           0.5 mm offset; x/y/z omitted until coordinates exist
acquisition/
  ElectricalSeries         32 x N int16, 20 kHz, conversion 1e-6 * spikeScalingToUv
  HeadstageAccelerometer   TimeSeries, N x 3, unit PROVISIONAL
  BehaviorVideoCam14 ...   ImageSeries external, timestamps = frame digital input rising edges
  CalibrationVideoCam14 .. ImageSeries external, rate 30.0, starting_time derived
intervals/
  human_interference       TimeIntervals, start_time (hi), stop_time (ho)
processing/behavior/
  BehavioralEvents/
    camera_frame_trigger   TimeSeries, digital input state at each transition
```

The partner's file is identical in shape with its own 32 channels, its own
`Subject`, and `../sub-0236/` paths in the `ImageSeries`.

### Step 4: Metadata plan (the `config.yaml` skeleton)

- **Session:** description template as above; `start_time` read from the
  `.rec` header, with the spreadsheet start time as a cross-check;
  `timezone: America/New_York` `PROVISIONAL`; `lab: Zhang Lab`;
  `institution: Michigan State University` `PROVISIONAL`; `experimenter`
  `PROVISIONAL`; `keywords`; `experiment_description` from the
  questionnaire; `related_publications` empty (none).
- **Subjects:** one block each for `0235`, `0236`, `0237` with species,
  `sex: U` `PROVISIONAL`, `age` `PROVISIONAL`, description from the
  identification marks.
- **Devices:** headstage (name, manufacturer SpikeGadgets, description),
  camera (Teledyne FLIR Blackfly S USB3), acquisition software Trodes.
- **Electrode groups and channel maps:** `belly_down` and `belly_up` maps
  as channel lists per region, reference channels, the 0.5 mm note,
  locations as free text (`premotor cortex`, `posterior parietal cortex`),
  coordinates `PROVISIONAL` and omitted.
- **Sync:** `frame_trigger_din: PROVISIONAL` (auto-detected by pulse rate
  until confirmed), expected camera ids `[14, 46, 58, 67, 68]`, video
  `rate: 30.0`.
- **Streams:** descriptions and units for the accelerometer and the
  `ElectricalSeries`, `filtering` `PROVISIONAL`.
- **Session log:** path to the committed `session_log.csv` and the parsing
  rules (belly-up flag, usable-data text, the PM rule for bare times).

### Implementation notes for the scaffold

- **Ephys reader.** NeuroConv's `SpikeGadgetsRecordingInterface`
  (spikeinterface, neo `SpikeGadgetsRawIO`) reads the `trodes` stream with
  the header gains, and that is the path for the `ElectricalSeries`. neo
  does not expose the digital inputs (it builds no event channels) and
  skips the interleaved headstage sensor block, so the frame trigger and
  the accelerometer need a small packet reader of our own. The packet
  layout is documented in neo's reader docstring (device blocks with
  `numBytes` and `startByte`, uint32 timestamp, int16 ephys region), so
  this is a memmap and a few bit masks, not a proprietary dependency. The
  SpikeGadgets `trodesexport` binary is the fallback if a real file shows
  something the docstring does not cover. The Frank lab's `trodes_to_nwb`
  was considered and not adopted: it dictates its own file naming, YAML
  metadata and Spyglass-oriented structure.
- **Time base.** Trodes packet timestamps over the header sampling rate
  give seconds from recording start. Use them rather than assuming a
  continuous sample count; wireless and datalogger recordings can have
  gaps, and a gap turns `rate + starting_time` into explicit timestamps.
- **Frame sync.** Rising edges of the frame digital input are the video timestamps.
  Compare the edge count with `ffprobe`'s frame count per video; a mismatch
  is reported, and the shorter of the two truncates, never silently.
- **Two animals, one file.** The header's nTrode assignments say which
  channels belong to which headstage; each subject file takes only its own
  32 channels. Until a real `.rec` is inspected, the mapping is
  `PROVISIONAL`.
- **Batch driver.** Standard dispatch contract: `--input`, `--output`,
  `--config`, `--overwrite`, `--jobs`, exit 0 on an empty incoming tree,
  tqdm over sessions, output parents created. A session counts as
  converted when both subject files exist. Sessions parallelize safely on
  memory (memmap reads, no video decode) but the video copies are I/O
  bound, so `--jobs` defaults to a small number and `code/README.md` says
  why. An incomplete upload (a `.rec` whose videos have not landed yet) is
  converted ephys-only with a report; dispatch marks it converted, so it is
  only revisited when the script hash changes. That is a dispatch
  limitation worth a follow-up issue, not something this lab fixes.
- **Runtime.** Python: pynwb, neuroconv with the spikegadgets extra,
  numpy, PyYAML, tqdm. System: FFmpeg (`ffprobe`). No MATLAB, no
  proprietary binaries.
- **Tests.** Golden-file pattern: a synthetic `.rec` (XML header plus a few
  hundred packets with a 30 Hz digital input, two headstages, a sensor block),
  tiny AVIs, a `.trodesComments` file and a two-row session log under
  `tests/example_raw/`; the two expected NWB files compared structurally
  (field by field, not byte-exact, since HDF5 is not deterministic).

### What sign-off needs

Answers to questions 1 through 4 and 12 through 15 change the code that
gets written; the rest can stay `PROVISIONAL` in `config.yaml` and be filled
in later. Approval and corrections get quoted below as further
`## Request N` sections.

## Request 2 — Plan sign-off

> 1. act like it does contain it and we will go from there; use the neuroconv interface to handle all that metadata
> 2. ferret-hyperscanning
> 3. nwb in dandi layout
> 4. keep avi for now we will transcode later
> 5. well deal with time sync in a followup
> 6. will get back to you on trodes comment
> 7. ...the rest, we will do in follow-ups

Read against the plan's numbered questions: the `.rec` is treated as the
merged file holding both headstages' ephys, read through NeuroConv's
SpikeGadgets interface, which also supplies the device, electrode-group and
electrode-table metadata; the layout is nested,
`labs/zhang/ferret-hyperscanning/`; the standard is option A, NWB with one
file per subject per session in DANDI's `sub-<id>/` layout; the AVIs are
carried unchanged as external files; frame-pulse synchronization, the
Trodes comments, and every other open question are follow-ups. Until the
sync follow-up, the video `ImageSeries` carry the nominal 30 fps rate with
a `PROVISIONAL` starting time of zero, and the headstage accelerometer and
human-interference intervals are not written.

Between the plan and this sign-off the branch also picked up a `zarr<3`
bound in every neuroconv-based lab environment: hdmf-zarr 0.14.0 was
released the same day and moved to zarr 3, which neuroconv 0.10.2 cannot
import under. The Zhang environment carries the same bound.

## Request 3 — Use NeuroConv's video interface

> use the neuroconv video interface instead of direct imageseries

Each subject's file is now assembled by a NeuroConv `ConverterPipe` that
combines the SpikeGadgets interface with one `ExternalVideoInterface` per
video file. The video interface reads each file's frame rate and frame count
from its header and links the camera device. It stores the absolute path it
read, so the converter rewrites each `external_file` relative to the NWB
file before writing. The golden output summary came out unchanged.

## Request 4 — A separate open-questions doc

> separate the open questions into a clearly designated and linked doc for future reference

The plan's questions now live in `../OPEN_QUESTIONS.md`, keeping their
numbers (Q1 to Q15, plus Q16 on DANDI's validation of the `.avi` assets).
Each question carries its status after the sign-off, what it blocks, and
where its placeholder lives. The lab README, the `PROVISIONAL` comments in
`code/config.yaml`, and the dispatch note link to it.

## Request 5 — Drop two questions

> remove Q1 and Q6 those will become self-explanatory

Q1 (whether the uploaded `.rec` holds the ephys) and Q6 (where the Trodes
comments live) are removed from `../OPEN_QUESTIONS.md`. The other questions
keep their numbers.

## Request 6 — Generalize Q5

> keep Q5 worded just as general 'request information regarding temporal synchronization protocols'

Q5 in `../OPEN_QUESTIONS.md` is now "Temporal synchronization protocols",
asking the lab for information on them, without the timestamp specifics.

## Request 7 — Spell out digital input

> dont use DIN as abbreviation

Every "DIN" in this lab's docs, including the plan above and Q7 of
`../OPEN_QUESTIONS.md`, now reads "digital input".
