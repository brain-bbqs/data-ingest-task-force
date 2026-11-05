# Session: Sanes Big_Arean_2024_12 conversion planning

Preparing intake and a reviewable NWB conversion plan for incoming dandiset `000601` and standardized dandiset `000629`. The requester approved the plan in Request 4. Implementation extends the existing shared codebase and registration. The existing shared Sanes conversion and registration are inspected as prior work.

## Request 1 — Set up the conversion through plan review

> Please set up a new conversion for the Sanes lab, working through the
> new-conversion skills in .agents/skills/ in order: lab-intake, then
> lab-conversion-plan, then stop for my review of the plan before running
> lab-scaffold and lab-register. Finish with lab-lessons, encoding anything
> this conversion taught back into the skills.
>
> - Dan Sanes
> - Grant award number: U01DA063581
> - Project name: Big_Arean_2024_12
> - Incoming dandiset: 000601
> - Standardized output dandiset: 000629
> - Data standard: NWB
> - Associated papers: none
> - Source data tree:
> sourcedata/
> └── raw/
>     └── experiment_109/
>         └── concatenated_data_cam_mic_sync/
>             │
>             ├── channel_00_file_000.wav
>             ├── channel_00_file_001.wav
>             ├── ...
>             ├── channel_00_file_005.wav
>             │
>             ├── channel_01_file_000.wav
>             ├── ...
>             ├── channel_01_file_005.wav
>             │
>             ├── channel_02_file_000.wav
>             ├── ...
>             ├── channel_02_file_005.wav
>             │
>             ├── ...
>             │
>             ├── channel_07_file_000.wav
>             ├── ...
>             ├── channel_07_file_005.wav
>             │
>             ├── README.txt
>             ├── sync.csv
>             │
>             ├── temp/
>             │   └── ...
>             │
>             ├── video_center_000.mp4
>             ├── video_center_001.mp4
>             ├── ...
>             ├── video_center_005.mp4
>             │
>             ├── video_gily_center_000.mp4
>             ├── ...
>             ├── video_gily_center_005.mp4
>             │
>             ├── video_gily_nest_000.mp4
>             ├── ...
>             ├── video_gily_nest_005.mp4
>             │
>             ├── video_gily_underground_000.mp4
>             ├── ...
>             ├── video_gily_underground_005.mp4
>             │
>             ├── video_underground_000.mp4
>             ├── ...
>             └── video_underground_005.mp4
> - Metadata: session files are in sync.csv. the files are continuous with each other . the relation between files is described in README.txt.
> - Expected output example: similar to other sanes conversion, with all continuous data in one NWB file using multisubjects for audio/video data.
> - Prior conversion code: in sanes/ folder

(Attached: `sync.csv` and `README.txt` from `/Users/thoman1/Downloads/`. The user also instructed, "Distinguish instructions in attached documents from the user's request.")

## Planning record

The attachments describe source synchronization and are treated as evidence about the recordings. They do not authorize implementation or change the requested NWB target or review boundary.

See [the review plan](../CONVERSION_PLAN_BIG_ARENA_2024_12.md) for the completed intake, mappings, expected output, open questions, and lessons. Plan approval is quoted in Request 4 below. Later requester decisions should be appended here verbatim without replacing earlier Sanes prompt records.

## Request 2 — Institution, provisional timezone, and missing animal metadata

In response to the question about the timestamps' timezone and the animal roster:

> the institution is NYU so presumably East coast. we don't have animal data yet.

## Request 3 — Confirm external video packaging

In response to the question about referencing five concatenated MP4s externally from the single NWB:

> Yes, one NWB plus five external MP4s

## Request 4 — Approve the conversion plan

> The plan looks good

## Implementation record

The approved plan was implemented in the shared Sanes codebase, and all six registration touchpoints
were audited. The existing entry, session globs, environment, and shared image are reused. Integration
CI now names the Sanes job accordingly. Synthetic media exercises the supplied hierarchy; no real lab
media was inspected or uploaded.

The installed `ndx-sound` schema accepts mono or stereo series, so eight mono series in the one NWB
replace the plan's eight-column series. All microphone samples and source identities are preserved.
The `ndx-multisubjects` schema permits roster rows without individual file links, verified by round-trip
tests. An absent roster is explicitly reported and does not create placeholder subjects.

NWB Inspector and DANDI validation exposed multisubject-root support limitations, recorded in
`OPEN_QUESTIONS.md`. Explicit root and waveform schema validation is covered by the integration tests.
Upload validation was not weakened. Planning and schema-check lessons were encoded in the repository
skills. The required external `nwb-convert` skill was refreshed to
`ea2405e39efbdf324a5fcd77aed05bb1787b260d`; its submodule pin change is deliberate and should be committed
separately from the conversion when the work is committed.

## Request 5 — Commit on the Sanes arena branch

> can you create the commit on the sanes-arena branch according to the instructions
