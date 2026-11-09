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

See [the conversion plan](big-arena-2024-12-plan.md) for the completed intake, mappings, expected output, open questions, and the amendments made after approval. Plan approval is quoted in Request 4 below. Later requester decisions should be appended here verbatim without replacing earlier Sanes prompt records.

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
CI now names the Sanes job accordingly. Synthetic media exercises the supplied hierarchy. No real lab
media was inspected or uploaded.

This implementation first split the audio into eight mono series, on the belief that `ndx-sound`
accepts only mono or stereo. That held for 0.2.3 only, and Request 7 restored the plan's single
eight-column series. All microphone samples and source identities are preserved.
The `ndx-multisubjects` schema permits roster rows without individual file links, verified by round-trip
tests. An absent roster is explicitly reported and does not create placeholder subjects.

NWB Inspector and DANDI validation exposed multisubject-root support limitations, recorded in
`OPEN_QUESTIONS.md`. Explicit root and waveform schema validation is covered by the integration tests.
Upload validation was not weakened. Planning and schema-check lessons were encoded in the repository
skills. The required external `nwb-convert` skill was refreshed to
`ea2405e39efbdf324a5fcd77aed05bb1787b260d`. Its submodule pin change is deliberate and should be committed
separately from the conversion when the work is committed.

## Request 5 — Commit on the Sanes arena branch

> can you create the commit on the sanes-arena branch according to the instructions

## Request 6 — Address the pull request review

From the reviewer (CodyCBakerPhD), after the
[review](https://github.com/brain-bbqs/data-ingest-task-force/pull/53#pullrequestreview-5762511679) of the
pull request:

> https://github.com/brain-bbqs/data-ingest-task-force/pull/53 do the things the review says

Earlier on the pull request, the requester had commented:

> yes that would be great if you can handle those details! I think this new PR should work for both the arena datasets (BIG_ARENA_2025_03 and BIG_ARENA_2024_12) - could you confirm?

The changes since approval that need the requester's confirmation are Q16 and Q17 in `OPEN_QUESTIONS.md`.
BIG_ARENA_2025_03 now gets the same provisional timezone (Q9), and its layout is still uninspected (Q6).

## Request 7 — Decide the open review questions

From the reviewer (CodyCBakerPhD), answering Q16, the three parts of Q17, and the widened lab-intake rule. The first and last lines quote the agent's explanation.

> "Keep stopping (current). Safest, and a person looks at every case."
>
> for Q17 (a), if each audio file is mono, then yeah stack as 8-col so we only have one array
>
> Q17 (b) yeah keep a note, it belongs on Dandiset metadata
>
> Q17 (c) keep it its useful
>
> "Now: a collection with a different layout can also join, if its output follows the same conventions and the converter gains a second reader for the new layout." yeah that sounds fine

The audio is now one eight-column series with `ndx-sound>=0.3.0`. The plan is kept as `big-arena-2024-12-plan.md` beside this record, amended to match the implementation. Q16 and Q17 are resolved.
