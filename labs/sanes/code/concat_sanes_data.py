# Original conversion script developed by Neha Thomas (neha-thomas477), committed
# verbatim as provenance. This is one of the v2 scripts that supersede the v1
# notebook (sanesDatatoNWB_v2.ipynb, retired from the tree; see git history and
# ../README.md) this repository originally ported. It merges every chunk's
# SLEAP .slp file into one Labels object, splits it by track, and writes one
# NWB per track (with a Subject built from config_multisubject.yaml) plus the
# concatenated chunk videos into one combined_output.mp4. See ../README.md for
# how it is treated here.

# %% libraries
import os
import sys


from natsort import natsorted
import sleap_io as sio
from sleap_io.model.matching import PATH_VIDEO_MATCHER
import ffmpeg
import subprocess
import json
import argparse
from pathlib import Path
from datetime import datetime
from pynwb import NWBHDF5IO, NWBFile
from pynwb.file import Subject

print("cwd:", os.getcwd())
print("PYTHONPATH:", os.environ.get("PYTHONPATH"))
print("sys.path:")
for p in sys.path:
    print("  ", p)

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
    
from utils import config



# %% CLI argument parsing

def parseargs():
    parser = argparse.ArgumentParser(
        description="Concatenate SLEAP .slp files and video files from idx_* folders."
    )
    parser.add_argument(
        "--file_path", "-f",
        type=str,
        required=True,
        help="Path to the folder containing idx_* subdirectories with .slp and .mp4 files"
    )
    parser.add_argument(
        "--output_dir", "-o",
        type=str,
        default=None,
        help="Output directory for merged files (default: <file_path>/Split_SLPs)"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to config YAML file (default: <file_path>/config_multisubject.yaml)"
    )
    args = parser.parse_args()

    file_path = Path(args.file_path)
    out_dir = Path(args.output_dir) if args.output_dir else file_path / "Split_SLPs"

    # Load config file
    config_path = Path(args.config) if args.config else file_path / "config_multisubject.yaml"
    cfg = config.load_cfg(config_path)

    return file_path, out_dir, cfg
# %% 
def get_video_info_ffprobe(video_path):
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=duration,nb_frames,r_frame_rate',
        '-of', 'json',
        video_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    info = json.loads(result.stdout)
    
    stream = info['streams'][0]
    duration = float(stream.get('duration', 0))
    frame_count = int(stream.get('nb_frames', 0))
    return duration, frame_count

# %% merge the separate .slp files into single .slp - RUN ONLY ONCE!

def get_slp_files(file_path):
# get all idx_# directories
    folders = [f for f in file_path.iterdir() if f.is_dir() and f.name.startswith("idx_")]
    folders = natsorted(folders)

    # collect all .slp files 
    slp_files = natsorted([str(slp) for folder in folders for slp in Path(folder).glob("*.slp")])

    print("Found SLP files:")
    print("\n".join(slp_files))
    baseLabels = sio.load_file(slp_files[0])
    skeleton = baseLabels.skeletons[0]
   

    for slp_path in slp_files[1:]:
        
        labels_new = sio.load_file(slp_path)
        #for vid in labels_new.videos:
        #matcher = VideoMatcher(method=VideoMatchMethod.PATH, strict=True)  # exact path match
        baseLabels.merge(labels_new, video_matcher=PATH_VIDEO_MATCHER, frame_strategy="keep_both")
        #baseLabels.save( 'merged_labels.slp' )
    return baseLabels

# %% SLEAP labels

def create_merged_slp_tracks(baseLabels, out_dir, cfg):
    #from sleap_io.model import Labels
    # convert merged .slp to nwb with pose data
    print(baseLabels)

    track_labels_list = []  # store one Labels per track

    for track in baseLabels.tracks:
        print(f"Extracting {track.name} ...")

        # select frames that contain instances from this track
        lf_sub = []
        for lf in baseLabels.labeled_frames:
            instances = [inst for inst in lf.instances if inst.track == track]
            if instances:
                # make a shallow copy of the frame containing only those instances
                new_lf = lf.__class__(video=lf.video, frame_idx=lf.frame_idx, instances=instances)
                lf_sub.append(new_lf)

        # build a new Labels object for this track
        track_labels = sio.Labels(
            labeled_frames=lf_sub,
            videos=baseLabels.videos,          # keep all videos for reference
            skeletons=baseLabels.skeletons,    # keep same skeleton
            tracks=[track],                    # only this track
        )

        track_labels_list.append(track_labels)
        print(f"  -> {len(lf_sub)} frames for {track.name}")

    print(f"\nCreated {len(track_labels_list)} per-track Labels objects.")

# save the per-track Labels objects

    out_dir.mkdir(parents=True, exist_ok=True)

    for track_idx, track_labels in enumerate(track_labels_list):
        track_name = track_labels.tracks[0].name or f"track_{track_labels.tracks[0].id}"
        out_path = out_dir / f"{track_name}.slp"
        nwb_path = out_dir / f"{track_name}.nwb"

        n_total_instances = sum(len(lf.instances) for lf in track_labels.labeled_frames)
        print(track_labels.tracks[0].name, "instances:", n_total_instances)

        track_labels.save(str(out_path))

        if nwb_path.exists():
            nwb_path.unlink()
            print(f"Removed existing {nwb_path}")

        # Get subject information from config based on track index
        subject_key = f"subject_{track_idx}"
       
        
        subject = Subject(
            subject_id=config.cfg_get(subject_key, "id", CFG=cfg),
            species=config.cfg_get(subject_key, "species", CFG=cfg),
            sex=config.cfg_get(subject_key, "sex", CFG=cfg),
            age=config.cfg_get(subject_key, "age", CFG=cfg),
            description=config.cfg_get(subject_key, "description", CFG=cfg),
        )

        identifier = f"Subject_{subject.subject_id}"
        session_description = f"SLEAP tracking data for {subject.subject_id}"
        experimenter = config.cfg_get("session", "experimenter", CFG=cfg)
        institution = config.cfg_get("session", "institution", CFG=cfg)
        date_string = config.cfg_get("session", "start_time", CFG=cfg) 
        date_format = "%Y-%m-%d%H:%M:%S%z"
        session_start_time = datetime.strptime(date_string, date_format)
        # Save NWB with subject
        sio.io.nwb.write_nwb(track_labels, str(nwb_path), nwb_file_kwargs={'session_description': session_description, 
                                                                            'identifier': identifier, 'session_start_time': session_start_time, 
                                                                               'experimenter': experimenter, 'institution': institution, 'subject': subject})
       
        print(f"Saved {out_path}")

# %% Concatenate video files

def concat_video_files(file_path):

    # get all the idx_0 directories
    folders = [f for f in os.listdir(file_path) if os.path.isdir(os.path.join(file_path, f)) and f.startswith('idx_')]
    # sort the folders in natural order
    folders = natsorted(folders)
    vid_files = []
    cumulative_offset = 0.0
    vidStartFrames = []
    vidStartFrames.append(cumulative_offset)
    for folder in folders:
        folder_path = os.path.join(file_path, folder)
    # -- only need to run this once ever to create the combined file -- 
        vid_file = [f for f in os.listdir(folder_path) if f.endswith('.mp4')]
        vid_file = vid_file[0]
        vid_path = os.path.join(folder_path, vid_file)
        duration, frame_count = get_video_info_ffprobe(vid_path)
        print(f"Video: {vid_file}, Duration: {duration} seconds, Frame Count: {frame_count}")
        #print(os.path.join(folder_path,vid_file))
        vid_files.append(vid_path)

        cumulative_offset += duration
        vidStartFrames.append(frame_count + vidStartFrames[-1])
    # loop through vid_files and concatenate videos into one big video
    # Step 1: Convert each input .mp4 to .ts (MPEG Transport Stream)
    ts_files = []
    for file in vid_files:
        ts_file = file.replace('.mp4', '.ts')
        ffmpeg.input(file).output(ts_file, format='mpegts', vcodec='copy', acodec='copy').run(overwrite_output=True)
        ts_files.append(ts_file)

    # Step 2: Concatenate all .ts files into a single MP4
    concat_str = '|'.join(ts_files)
    print(concat_str)
    ffmpeg.input(f'concat:{concat_str}', format='mpegts') \
        .output(os.path.join(file_path,'combined_output.mp4'), vcodec='copy', acodec='copy') \
        .run(overwrite_output=True)

    # Optional: clean up intermediate .ts files
    for ts_file in ts_files:
        os.remove(ts_file)
# %% main
def main():
    file_path, out_dir, cfg = parseargs()
    baseLabels = get_slp_files(file_path)
    create_merged_slp_tracks(baseLabels, out_dir, cfg)
    concat_video_files(file_path)

# %% Run main
if __name__ == "__main__":
    main()
