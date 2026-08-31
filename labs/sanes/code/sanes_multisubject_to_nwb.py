# Original conversion script developed by Neha Thomas (neha-thomas477), committed
# verbatim as provenance. This is one of the v2 scripts that supersede the v1
# notebook (sanesDatatoNWB_v2.ipynb, retired from the tree; see git history and
# ../README.md) this repository originally ported. It builds the top-level
# session NWB file linking to the per-track NWBs concat_sanes_data.py produces.
# See ../README.md for how it is treated here and ../code/README.md for how the
# callable v2 port (_sanes_to_nwb.py) differs from it.

import sys
import os
from natsort import natsorted
from pynwb import NWBHDF5IO
from pynwb.image import ImageSeries
from scipy.io import wavfile
from pynwb.epoch import TimeIntervals
from pathlib import Path

from datetime import datetime
import argparse
import numpy as np
import pandas as pd

import json
import subprocess
from ndx_sound import AcousticWaveformSeries
from ndx_multisubjects import (
    NdxMultiSubjectsNWBFile,
    SubjectsTable,

)
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from neuroconv.tools import configure_and_write_nwbfile


print("cwd:", os.getcwd())
print("PYTHONPATH:", os.environ.get("PYTHONPATH"))
print("sys.path:")
for p in sys.path:
    print("  ", p)
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from utils import config


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Combine files in idx folders and convert to NWB"
    )
    p.add_argument(
        "--inputFolder", required=True, type=Path, help="Path to idx folders"
    )
    p.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="YAML config (default: ./config.yaml)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output NWB file path (default: derive from --mat)",
    )
    return p.parse_args()

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

def build_nwb(out_path, input_path, cfg):
    """
    Assemble an :pyclass:`pynwb.NWBFile` from MATLAB *data* and write *out_nwb*.

    The function is intentionally large but linear: parse metadata → convert
    timestamps → create NWB containers → write to disk.

    Parameters
    ----------
    data: Output of :pyfunc:`pymatreader.read_mat` containing both data (``d_*``) and timing (``ntp_*``) arrays.
    subject_name: String identifier for the human participant (e.g. ``"03"``).
    session: Walk session number starting from 1.
    out_nwb: Path to the target ``.nwb`` file (will be overwritten).
    cfg: Parsed YAML configuration with recording‑specific metadata.

    Returns
    -------
    None
    *The NWB file is written as a side effect. A short confirmation message is printed*
    """

    date_string = config.cfg_get("session", "start_time", CFG=cfg)
    date_format = "%Y-%m-%d%H:%M:%S%z"
    session_start = datetime.strptime(date_string, date_format)

    # create NWB file
    nwbfile = NdxMultiSubjectsNWBFile(
        session_description=config.cfg_get(
            "session", "description", CFG=cfg
        ),  # hardcode what session is/information in this block
        identifier="Sanes-Multisubject-1",
        session_start_time=session_start,
        experimenter=config.cfg_get("session", "experimenter", CFG=cfg),
        institution=config.cfg_get("session", "instituition", CFG=cfg),
    )

    subjects_table = SubjectsTable(
    description="Subjects in this session",
)
    parent_path = out_path.parent
    subjects_table.add_row(
 
    species=config.cfg_get("subject_0", "species", CFG=cfg),
    subject_id=config.cfg_get("subject_0", "id", CFG=cfg),
    age=config.cfg_get("subject_0", "age", CFG=cfg),
    sex=config.cfg_get("subject_0", "sex", CFG=cfg),

    # get parent path of out_path and then get relative path to the individual subject nwb file
    
    individual_subj_link = os.path.relpath(str(parent_path / "sub-00" / "track_0.nwb"), os.path.dirname(out_path))
)
    
    subjects_table.add_row(
 
    species=config.cfg_get("subject_1", "species", CFG=cfg),
    subject_id=config.cfg_get("subject_1", "id", CFG=cfg),
    age=config.cfg_get("subject_1", "age", CFG=cfg),
    sex=config.cfg_get("subject_1", "sex", CFG=cfg),
    individual_subj_link=os.path.relpath(str(parent_path / "sub-01" / "track_1.nwb"), os.path.dirname(out_path))
)
    subjects_table.add_row(
 
    species=config.cfg_get("subject_2", "species", CFG=cfg),
    subject_id=config.cfg_get("subject_2", "id", CFG=cfg),
    age=config.cfg_get("subject_2", "age", CFG=cfg),
    sex=config.cfg_get("subject_2", "sex", CFG=cfg),
    individual_subj_link=os.path.relpath(str(parent_path / "sub-02" / "track_2.nwb"), os.path.dirname(out_path))
)
    nwbfile.subjects_table = subjects_table





    # get all the idx_0 directories
    folders = [f for f in os.listdir(input_path) if os.path.isdir(os.path.join(input_path, f)) and f.startswith('idx_')]
    # sort the folders in natural order

    folders = natsorted(folders)


    #print(folders)
    # get all the .wav files in the directory

    audiochannel_data = []

    vid_files = []
    vox_data = []
   



    # registry so identical skeletons are created once and then reused


    # vox_data = TimeIntervals(name='vocalizations')
    # vox_data.add_column(name = 'name')
    # vox_data.add_column(name = 'channel')
    cumulative_offset = 0.0
    vidStartFrames = []
    vidStartFrames.append(cumulative_offset)
    # cache metadata once per animal/track
    # What we’ll copy directly onto PoseEstimation later


    # loop through each folder
    for folder in folders:
        folder_path = os.path.join(input_path, folder)
        wav_files = [f for f in os.listdir(folder_path) if f.endswith('.wav') and 'multichannel' not in f]
        wav_files = natsorted(wav_files)  
        # read the annotations.csv file
        
        channel_columns = []
        for wav_file in wav_files:
            this_file_path = os.path.join(folder_path, wav_file)
            #print(this_file_path)
            audio_sampling_rate, thisData = wavfile.read(this_file_path)  
            #append data as column in audiochannel_data
            thisData = thisData.reshape(-1, 1)
            # data = np.hstack((data, thisData.reshape(-1, 1)))
            channel_columns.append(thisData)

        data = np.hstack(channel_columns)
        audiochannel_data.append(data)
    #print(audiochannel_data)

        vid_file = [f for f in os.listdir(folder_path) if f.endswith('.mp4')]
        vid_file = vid_file[0]
        vid_path = os.path.join(folder_path, vid_file)
        duration, frame_count = get_video_info_ffprobe(vid_path)
        print(f"Video: {vid_file}, Duration: {duration} seconds, Frame Count: {frame_count}")
        #print(os.path.join(folder_path,vid_file))
        vid_files.append(vid_path)

        # vocalizations data
        annotationsPath = os.path.join(folder_path, 'annotations.csv')
        df = pd.read_csv(annotationsPath)
        df.start_seconds = df.start_seconds + cumulative_offset
        df.stop_seconds = df.stop_seconds + cumulative_offset
        # append df to vox_data
        vox_data.append(df)
        cumulative_offset += duration
        vidStartFrames.append(frame_count + vidStartFrames[-1])
        
   
                

                

    



    print(vidStartFrames)  



    # stack the audio data into a single array

    multichannel_data = np.concatenate(audiochannel_data,axis = 0)
    # stack into shape (n_smaples, n_channels)
    #audio_matrix = np.stack(multichannel_data, axis=-1)


    acoustic_waveform_series = AcousticWaveformSeries( # got an error with dandi validate complaining about # channels
        name='Multi-channel Acoustic Data',
        description="Audio data from 12 channels",
        data = multichannel_data,
        rate = float(audio_sampling_rate),

    )


    nwbfile.add_acquisition(acoustic_waveform_series)






    #externalFile = [os.path.relpath(os.path.join(file_path, 'combined_output.mp4'), os.path.dirname(nwbfile_path))]
    externalFile = [os.path.relpath(f, os.path.dirname(out_path)) for f in vid_files]

    print(externalFile)
    sampling_rate = 30.0  # Assuming a default frame rate for the video

    starting_frames = np.asarray(vidStartFrames[:-1], dtype=np.int64)
        # create an ImageSeries for each mp4 file
    extBehVideos = ImageSeries(
        name="External Behavioral Videos",
        unit='n.a.',
        starting_time=0.0,
        starting_frame = starting_frames,
        rate=sampling_rate,
        description="External video file combined from multiple videos",
        external_file= externalFile,  # Path to the video file
        format = "external",
    )
    nwbfile.add_acquisition(extBehVideos)   

    # create behavviorModule
    behaviorModule = nwbfile.create_processing_module(
        name='behavior',
        description='Vocalization annotations'
    )
    # Step 1: Concatenate all annotation DataFrames
    all_vox_df = pd.concat(vox_data, ignore_index=True)

    # Step 2: Rename time columns to match NWB
    all_vox_df = all_vox_df.rename(columns={
        'start_seconds': 'start_time',
        'stop_seconds': 'stop_time',
        'name': 'label'
    })

    # Step 3: Create TimeIntervals from DataFrame
    vocalizations_table = TimeIntervals.from_dataframe(
        name='vocalizations',
        df=all_vox_df
    )


    # print(all_vox_df.iloc[5000,:])
    behaviorModule.add_container(vocalizations_table)

    externalFile = [os.path.relpath(os.path.join(input_path, 'combined_output.mp4'), os.path.dirname(out_path))]

    # loop through mp4_files and add them to ImageSeries 
    print(externalFile)
    sampling_rate = 30.0  # Assuming a default frame rate for the video

    
        # create an ImageSeries for each mp4 file
    extBehVideos = ImageSeries(
        name="External Behavioral Video (Combined)",
        unit='n.a.',
        starting_time=0.0,
        rate=sampling_rate,
        description="External video file combined from multiple videos",
        external_file= externalFile,  # Path to the video file
        format = "external",
    )
    nwbfile.add_acquisition(extBehVideos)   

    # Get the default backend configuration
    backend_configuration = get_default_backend_configuration(nwbfile, backend="hdf5")

    # Apply gzip compression with zstd compressor to all datasets
    backend_configuration.apply_global_compression(
    compression_method="gzip",
    compression_options={
        "compression_opts": 4  # gzip level: 1 (fastest) to 9 (smallest)
        }
    )
    # save the nwb file

    #configure_and_write_nwbfile(nwbfile, nwbfile_path = out_path, backend_configuration=backend_configuration)

    # write nwb file without compression regular way. 
    with NWBHDF5IO(str(out_path), 'w') as io:
        io.write(nwbfile)
    


def main():
    # usage
    args = parse_args()

    cfg = config.load_cfg(args.config)
    input_path = args.inputFolder
    out_path = args.out / "sanes_multisubject_1.nwb" 
   
    print(out_path)
    build_nwb(out_path=out_path,input_path = input_path, cfg=cfg)

    


if __name__ == "__main__":
    """
    Example CLI usage
    --------
    python sanes_multisubject_to_nwb.py --inputFolder exampleData/ --config ./config_multisubject.yaml --out ./Sanes-S01-MultiSubject.nwb
    """
    print("calling main")

    main()
