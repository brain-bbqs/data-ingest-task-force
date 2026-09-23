# Open questions

The questions this conversion still depends on, and where their answers
land. Numbers match the conversion plan in `prompts/initial.md`, so they
stay citable from follow-up PRs, commit messages and the `PROVISIONAL`
comments in `code/config.yaml`. Q16 and Q17 were added after the plan.

When a question is answered, quote the answer into `prompts/initial.md` as
a new request, make the code change, and move the entry to "Resolved" below
with a pointer to the change.

## Status at a glance

| # | Question | Status | Blocks |
| --- | --- | --- | --- |
| [Q5](#q5-temporal-synchronization-protocols) | Request information regarding temporal synchronization protocols | Deferred to the sync follow-up | Video timing |
| [Q7](#q7-which-digital-input-carries-the-camera-frame-trigger) | Which digital input carries the camera frame trigger? | Deferred to the sync follow-up | Video timing |
| [Q8](#q8-channel-numbering-per-headstage) | How are channels split between the two headstages? | Deferred | Correct ephys in every file |
| [Q9](#q9-subject-and-session-metadata) | Sex, age, experimenters, institution, timezone | Deferred | DANDI-ready metadata |
| [Q10](#q10-electrodes) | Electrode type, geometry, coordinates, filtering, references | Deferred | Electrode table detail |
| [Q11](#q11-accelerometer) | Accelerometer units and real sample rate | Deferred | Accelerometer stream |
| [Q12](#q12-session-log-as-an-input) | Session log as a committed CSV, and its parsing rules | Implemented as proposed, unconfirmed | Channel map selection, notes |
| [Q13](#q13-two-recordings-on-one-date) | Layout of days with two recordings of one pair | Implemented as proposed, unverified | Video matching |
| [Q14](#q14-sessions-to-exclude) | Should sessions without usable data be excluded? | Deferred, all converted | Which sessions publish |
| [Q15](#q15-calibration-videos) | Calibration videos in the NWB or as plain assets? | Implemented as proposed, unconfirmed | Calibration video placement |
| [Q16](#q16-investigate-video-transcoding) | Investigate video transcoding | Deferred to a follow-up | Video size and format |
| [Q17](#q17-implement-multisubject) | Implement multisubject | Deferred to a follow-up | One file linking each session's pair |

## Deferred to follow-ups

### Q5. Temporal synchronization protocols

- **Ask the lab:** request information regarding temporal synchronization
  protocols.
- **Current handling:** every video starts at the recording start,
  `video.starting_time` in `code/config.yaml`, marked `PROVISIONAL`.

### Q7. Which digital input carries the camera frame trigger?

The lab says one digital input pulses once per camera frame, with all five
cameras triggered together.

- **Ask the lab:** which digital input channel, and is each camera's first frame the
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
  `PROVISIONAL`). The header of a real merged file settles this.

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

### Q16. Investigate video transcoding

- **Follow-up work:** investigate video transcoding.
- **Current handling:** the AVIs are carried into the standardized
  dandiset unchanged, about 172 GB per session (Request 2).

### Q17. Implement multisubject

- **Follow-up work:** implement multisubject.
- **Current handling:** each session writes one NWB file per animal, and
  each file names its partner only in its description and notes.
- **Likely shape:** a session-level file linking the two per-animal files
  through `ndx-multisubjects`, the Sanes pattern. It can be added on top of
  the current output without redoing the ephys.

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
