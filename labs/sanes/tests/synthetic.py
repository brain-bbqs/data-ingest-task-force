"""Synthesize a Sanes session from the source layout the lab described, with any mix of data types.

Each session has chunks of ``CHUNK_SAMPLES`` audio samples and ``CHUNK_FRAMES`` video frames. Pose is written
either as SLEAP ``.slp`` files or as SLEAP CSV exports (``.tracks.csv``), with two tracks per chunk. FFmpeg must
be on PATH to write the videos.
"""

import csv
import subprocess

import numpy
import scipy.io.wavfile
import sleap_io

AUDIO_RATE = 1000
VIDEO_RATE = 10
CHUNK_SAMPLES = (500, 300)
CHUNK_FRAMES = (5, 3)
CHANNELS = 2
NODES = ("nose", "head", "tail_base")
EDGES = (("nose", "head"), ("head", "tail_base"))
LOG_START = "2025-08-12T11:01:09+00:00"

# (track, frame_idx, nose.x) per chunk. The second track_0 row has a missing nose.x.
POSE_ROWS = (("track_0", 0, 1.0), ("track_0", 2, None), ("track_1", 1, 4.0))


def _write_rows(*, path, fieldnames, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _point_values(*, nose_x, node_index):
    if node_index == 0:
        return (numpy.nan if nose_x is None else nose_x, 2.0, 0.9)
    return (10.0 + node_index, 20.0 + node_index, 0.8)


def _write_tracks_csv(*, path):
    fieldnames = ["track", "frame_idx", "instance.score"]
    for node in NODES:
        fieldnames += [f"{node}.x", f"{node}.y", f"{node}.score"]
    rows = []
    for track, frame_idx, nose_x in POSE_ROWS:
        row = {"track": track, "frame_idx": frame_idx, "instance.score": 0.95}
        for node_index, node in enumerate(NODES):
            x, y, score = _point_values(nose_x=nose_x, node_index=node_index)
            row.update({f"{node}.x": "" if numpy.isnan(x) else x, f"{node}.y": y, f"{node}.score": score})
        rows.append(row)
    _write_rows(path=path, fieldnames=fieldnames, rows=rows)


def _write_slp(*, path, video_path):
    skeleton = sleap_io.Skeleton(nodes=list(NODES), name="gerbil")
    skeleton.add_edges(list(EDGES))
    video = sleap_io.Video(filename=str(video_path), open_backend=False)
    tracks = {name: sleap_io.Track(name=name) for name in ("track_0", "track_1")}
    frames = {}
    for track, frame_idx, nose_x in POSE_ROWS:
        values = numpy.asarray([_point_values(nose_x=nose_x, node_index=index) for index in range(len(NODES))])
        instance = sleap_io.PredictedInstance.from_numpy(
            points_data=values[:, :2], skeleton=skeleton, point_scores=values[:, 2], score=0.95, track=tracks[track]
        )
        frames.setdefault(frame_idx, []).append(instance)
    labels = sleap_io.Labels(
        labeled_frames=[
            sleap_io.LabeledFrame(video=video, frame_idx=frame_idx, instances=instances)
            for frame_idx, instances in sorted(frames.items())
        ]
    )
    labels.save(str(path))


def write_session(
    *, root, name, chunk_format="idx_{:03d}", pose="tracks", audio=True, video=True, annotations=True, log=True
):
    """Write one session. *pose* is "tracks", "slp", or None."""
    session = root / name
    session.mkdir(parents=True)
    if log:
        (session / f"{name}_log_2025-08-12_11-01-09.txt").write_text(
            "2025-08-12_11-01-05>Initializing\n2025-08-12_11-01-09>Started Experiment Now\n"
        )
    for index, (samples, frames) in enumerate(zip(CHUNK_SAMPLES, CHUNK_FRAMES)):
        chunk = session / chunk_format.format(index)
        chunk.mkdir()
        if audio:
            for channel in range(CHANNELS):
                data = numpy.full(samples, fill_value=index + channel / 10, dtype=numpy.float32)
                scipy.io.wavfile.write(chunk / f"channel_{channel:02d}_file_{index:03d}.wav", AUDIO_RATE, data)
        video_path = chunk / f"video_gily_center_{index:03d}.mp4"
        if video:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size=32x32:rate={VIDEO_RATE}"]
                + ["-frames:v", str(frames), "-c:v", "mpeg4", "-pix_fmt", "yuv420p", str(video_path)],
                check=True,
            )
        if pose == "tracks":
            _write_tracks_csv(path=chunk / f"{index:03d}_video_gily_center_{index:03d}.tracks.csv")
        elif pose == "slp":
            _write_slp(path=chunk / f"{index:03d}_video_gily_center_{index:03d}.slp", video_path=video_path)
        if annotations:
            _write_rows(
                path=chunk / ("annotations.csv" if index == 0 else f"channel_0_{index}_annotations.csv"),
                fieldnames=["name", "start_seconds", "stop_seconds", "channel"],
                rows=[
                    {"name": "chirp", "start_seconds": 0.1, "stop_seconds": 0.15, "channel": 3},
                    {"name": "incomplete", "start_seconds": "", "stop_seconds": 0.2, "channel": 8},
                ],
            )
    return session
