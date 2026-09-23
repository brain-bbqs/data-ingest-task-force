# Open questions

The questions this conversion still depends on, and where their answers
land. Numbers match the conversion plan in `prompts/initial.md` (Q1 to
Q15), so they stay citable from follow-up PRs, commit messages and the
`PROVISIONAL` comments in `code/config.yaml`. Q16 was added during
scaffolding.

When a question is answered, quote the answer into `prompts/initial.md` as
a new request, make the code change, and move the entry to "Resolved" below
with a pointer to the change.

## Status at a glance

| # | Question | Status | Blocks |
| --- | --- | --- | --- |
| [Q1](#q1-does-the-uploaded-rec-contain-the-ephys) | Does the uploaded `.rec` contain the ephys? | Assumed yes, unverified | Correct ephys in every file |
| [Q5](#q5-camera-and-ephys-clocks) | Why do video and `.rec` timestamps differ by 40 minutes? | Deferred to the sync follow-up | Video timing |
| [Q6](#q6-where-are-the-trodes-comments) | Where are the Trodes `hi` / `ho` comments? | Waiting on the lab | Human-interference intervals |
| [Q7](#q7-which-din-carries-the-camera-frame-trigger) | Which DIN carries the camera frame trigger? | Deferred to the sync follow-up | Video timing |
| [Q8](#q8-channel-numbering-per-headstage) | How are channels split between the two headstages? | Deferred | Correct ephys in every file |
| [Q9](#q9-subject-and-session-metadata) | Sex, age, experimenters, institution, timezone | Deferred | DANDI-ready metadata |
| [Q10](#q10-electrodes) | Electrode type, geometry, coordinates, filtering, references | Deferred | Electrode table detail |
| [Q11](#q11-accelerometer) | Accelerometer units and real sample rate | Deferred | Accelerometer stream |
| [Q12](#q12-session-log-as-an-input) | Session log as a committed CSV, and its parsing rules | Implemented as proposed, unconfirmed | Channel map selection, notes |
| [Q13](#q13-two-recordings-on-one-date) | Layout of days with two recordings of one pair | Implemented as proposed, unverified | Video matching |
| [Q14](#q14-sessions-to-exclude) | Should sessions without usable data be excluded? | Deferred, all converted | Which sessions publish |
| [Q15](#q15-calibration-videos) | Calibration videos in the NWB or as plain assets? | Implemented as proposed, unconfirmed | Calibration video placement |
| [Q16](#q16-dandi-validation-of-the-avi-assets) | Does DANDI accept `.avi` files next to the NWB files? | Unknown until the first upload | Upload |

## Waiting on the lab

### Q1. Does the uploaded `.rec` contain the ephys?

By size it cannot. The example session's `.rec` is 764 MB over about 21
minutes at 20 kHz, about 31 bytes per packet, while 64 int16 channels alone
need 128. It reads like the base-station recording (sync, digital inputs,
timestamps), with the Sprite32 datalogger SD-card data not merged in or not
uploaded.

- **Current handling:** per the sign-off, the converter treats the `.rec`
  as the merged file holding both headstages. Run on the example upload, it
  would write whatever channels neo finds there.
- **Ask the lab:** is there a merged `.rec` per session, made with Trodes'
  datalogger merge or some other export? Where is it and how is it named?
- **If the ephys lives elsewhere:** the ephys rows of the mapping move to
  that file, and this `.rec` becomes the sync source only. That touches
  `build_nwbfile` in `code/_zhang_ferret_hyperscanning_to_nwb.py` and the
  discovery glob in `code/batch_convert.py` and `dispatch/sessions.json`.

### Q6. Where are the Trodes comments?

The lab marks human interference with Trodes comments `hi` (human in) and
`ho` (human out). Trodes normally writes them to `<rec>.trodesComments`
next to the `.rec`, and no such file is in the upload.

- **Current handling:** no intervals are written.
- **Once located:** they become an `intervals/human_interference`
  `TimeIntervals` table, start at `hi` and stop at `ho`, with unpaired
  comments reported.
- The requester is checking with the lab.

## Deferred to follow-ups

### Q5. Camera and ephys clocks

The behavior videos are stamped 12:24 and the calibration videos 12:18,
while the `.rec` is stamped 13:04 and the session log says 13:14 to 13:42.

- **Ask the lab:** is the camera computer's clock offset, or are these
  different recordings?
- **Why it matters:** alignment will come from the frame pulses (Q7), so
  this mainly affects placing the calibration videos and sanity checks.
- **Current handling:** every video starts at the recording start,
  `video.starting_time` in `code/config.yaml`, marked `PROVISIONAL`.

### Q7. Which DIN carries the camera frame trigger?

The lab says one digital input pulses once per camera frame, with all five
cameras triggered together.

- **Ask the lab:** which DIN channel, and is each camera's first frame the
  first pulse?
- **Follow-up work:** neo's SpikeGadgets reader does not expose the digital
  inputs, so this needs a small packet reader of our own. The rising edges
  become each video's `timestamps`, checked against the frame count. The
  converter can pick the channel pulsing near 30 Hz, but the channel should
  still be confirmed.

### Q8. Channel numbering per headstage

- **Ask the lab:** does the odd/even map (0 to 31) apply to each animal's
  32 channels separately? How does the `.rec` header say which nTrodes
  belong to `HS3` and which to `HS4`?
- **Current handling:** the first animal in the basename takes hardware
  channels 0 to 31 and the second 32 to 63 (`headstage_channel_ids`,
  `ecephys.channels_per_headstage` in `code/config.yaml`, marked
  `PROVISIONAL`). A real merged file settles this together with Q1.

### Q9. Subject and session metadata

- **Missing:** sex, age or date of birth, weight, experimenter names,
  institution where the data were collected, and timezone.
- **Current handling:** placeholders marked `PROVISIONAL` in the `session`
  and `subjects` blocks of `code/config.yaml`. Sex `U` and age `P1Y` are
  placeholders. Institution says Michigan State University, but the
  questionnaire contact is at UNC School of Medicine. Timezone is
  `America/New_York`.

### Q10. Electrodes

- **Missing:** electrode type and geometry, coordinates, impedances, the
  filtering applied, and whether channels 30 and 31 are recorded channels
  used as software references or hardware reference inputs.
- **Current handling:** locations are free text (`premotor cortex`,
  `posterior parietal cortex`), and channels 30 and 31 are flagged in the
  `reference_electrode` column. No coordinates are written.

### Q11. Accelerometer

- **Missing:** units or scale factor, and the real sample rate. The
  questionnaire says 20 kHz, while SpikeGadgets headstage sensors are
  usually interleaved at a much lower rate.
- **Follow-up work:** neo skips the headstage sensor block too, so this
  shares the packet reader with Q7. It will become
  `acquisition/HeadstageAccelerometer`.

### Q14. Sessions to exclude

29 of the 109 session-log rows have no usable-data value.

- **Ask the lab:** should those still be converted, and should anything be
  excluded outright?
- **Current handling:** every recording found is converted. Exclusions
  would go in `exclude` in `dispatch/sessions.json` or a flag in the
  session log.

### Q16. DANDI validation of the `.avi` assets

- **Unknown:** whether DANDI's default upload validation accepts the `.avi`
  files placed next to the NWB files under `sub-<id>/`. The only precedent
  for non-NWB assets, Kemere, keeps its BIDS tree under `sourcedata/`.
- **If it does not:** set `upload_validation: ignore` in
  `dispatch/projects.json`, or move the videos. The first real upload
  answers this.
- **Related:** transcoding the videos is a planned follow-up (Request 2).

## Implemented as proposed, awaiting confirmation

### Q12. Session log as an input

The session log is the only source of the belly-up flag and the usable-data
notes.

- **Current handling:** it is committed as `code/session_log.csv`, and the
  lab sends updates by editing that file. Two parsing rules were applied on
  export: the `4/23/206` date was read as 2026-04-23, and bare times with an
  hour below 8 were read as afternoon.
- **Ask the lab:** confirm both parsing rules.

### Q13. Two recordings on one date

Twelve date-pair combinations have two session-log rows.

- **Current handling:** each `.rec` is matched to the videos whose filename
  timestamp is nearest (`match_videos`), and to the session-log row whose
  start time is nearest (`find_session_row`).
- **Needs:** a real example of such a day, to confirm that both recordings
  share one `Videos/` directory.

### Q15. Calibration videos

- **Current handling:** the calibration videos are in the NWB as
  `CalibrationVideoCam<NN>`, starting at zero until Q5 and Q7 give them
  their real, earlier start times.
- **Ask the requester:** confirm that placement, as opposed to plain assets
  without an NWB reference.

## Resolved

| # | Question | Answer | Where |
| --- | --- | --- | --- |
| Q2 | Flat or nested lab layout | Nested, `labs/zhang/ferret-hyperscanning/` | Request 2 in `prompts/initial.md` |
| Q3 | Data standard | NWB, one file per subject per session, DANDI layout | Request 2 |
| Q4 | Video handling | Keep the AVIs unchanged as external files, transcode later | Request 2 |
