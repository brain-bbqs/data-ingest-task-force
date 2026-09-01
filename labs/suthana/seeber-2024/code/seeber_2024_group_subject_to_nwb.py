#!/usr/bin/env python3
"""
seeber_2024_group_subject_to_nwb.py
====================================
Original script author: Neha Thomas (as supplied for the Suthana lab's
"seeber-2024" project). Ported here verbatim as provenance.

Builds one group-level ``NdxMultiSubjectsNWBFile`` from the derived data
released alongside Seeber et al. (2024/2025), "Human neural dynamics of
real-world and imagined navigation". The source ``.mat`` files hold
per-figure analysis outputs (route models, wavelet power, reconstruction
errors, ...), not raw per-session recordings, which is why this is a
separate project from ``labs/suthana/in-lab/`` even though it shares the
same five de-identified subjects (``S1``..``S5``).

The only changes from the version handed to the ingest pipeline are the two
hardcoded local paths (``folder`` and ``saveNWBFolder``), which are now CLI
arguments instead of a specific machine's Box and Documents paths, and the
removal of five unused imports (``h5py``, ``timedelta``, ``tzlocal``,
``VectorData``, ``VectorIndex``). Nothing else has been adjusted yet: the
config-driven metadata, the CLI wrapper for ``batch_convert.py``, and the
electrode/subject-table hardcoding it inherited from the original script
are all pending the project's conversion plan. Kept unformatted and
unlinted as original provenance, like the Shepherd and Sanes ported files
(see ``.pre-commit-config.yaml``).
"""

import argparse
import os

import numpy as np
import pandas as pd

from datetime import datetime, timezone
from uuid import uuid4

from ndx_multisubjects import NdxMultiSubjectsNWBFile, SubjectsTable
from pynwb import TimeSeries
from pynwb.ecephys import ElectricalSeries
from neuroconv.tools.nwb_helpers import get_default_backend_configuration
from neuroconv.tools import configure_and_write_nwbfile
from pynwb.file import DynamicTable
from pynwb.misc import DecompositionSeries
from pynwb.behavior import BehavioralTimeSeries

from scipy.io import loadmat


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="Folder holding data_1.mat through data_4.mat directly. In the incoming"
        " dandiset these live under Seeber_etal_2024_data_code/data/, so pass that"
        " data/ subfolder's path, not Seeber_etal_2024_data_code/ itself.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Folder to write Zenodo_compressed_groupSubject.nwb into.",
    )
    return parser.parse_args()


args = parse_args()
folder = args.input
saveNWBFolder = args.output

nwbfile = NdxMultiSubjectsNWBFile(
    session_description="Data for Figures of Seeber et al., 2025: Human neural dynamics of real-world and imagined navigation",
    identifier=str(uuid4()),
    session_start_time=datetime.now(tz=timezone.utc)
)

subjects_table = SubjectsTable(
    description="Subjects in this experiment",
)

subjects_table.add_row(
    age="P36Y",
    subject_description="Subject S1",
    sex="M",
    species="Homo sapiens",
    subject_id="S1",
    individual_subj_link="relfilepath/sub-S1_ses-20220703T043729_behavior+ecephys.nwb"
)

subjects_table.add_row(
    age="P45Y",
    subject_description="Subject S2",
    sex="M",
    species="Homo sapiens",
    subject_id="S2",
    individual_subj_link="relfilepath/sub-S2_ses-20230723T012252_behavior+ecephys.nwb"
)

subjects_table.add_row(
    age="P24Y",
    subject_description="Subject S3",
    sex="F",
    species="Homo sapiens",
    subject_id="S3",
    individual_subj_link="relfilepath/sub-S3_ses-20230219T002943_behavior+ecephys.nwb"
)

subjects_table.add_row(
    age="P39Y",
    subject_description="Subject S4",
    sex="M",
    species="Homo sapiens",
    subject_id="S4",
    individual_subj_link="relfilepath/sub-S4_ses-20230811T134728_behavior+ecephys.nwb"
)

subjects_table.add_row(
    age="P30Y",
    subject_description="Subject S5",
    sex="F",
    species="Homo sapiens",
    subject_id="S5",
    individual_subj_link="relfilepath/sub-S5_ses-20220104T081228_behavior+ecephys.nwb"
)

nwbfile.subjects_table = subjects_table

# list all .mat files in this folder
files = [f for f in os.listdir(folder) if f.endswith(".mat")]
print(files)


filepath = os.path.join(folder, 'data_1.mat')
print(filepath)

matFile = loadmat(filepath)

left_route = matFile["route_L"]
right_route = matFile["route_R"]

iEEG_expl = matFile["iEEG_expl"]
Theta_expl = matFile["Theta_expl"]
# put route_L and Route_R into dynamic tables.

## ---- Second data file ----- ##

filepath = os.path.join(folder, 'data_2.mat')
matFile = loadmat(filepath)

walks_left = matFile["walks_left"] # in m
walks_right = matFile["walks_right"]

avg_theta_HPC_L = matFile["Theta_HPC_L"] # in z
avg_theta_HPC_R = matFile["Theta_HPC_R"] # in z

TF_expl_L = matFile["TF_expl_L"] # in z
TF_expl_R = matFile["TF_expl_R"] # in z

TF_turn = matFile["TF_turn"]
Theta_turn = matFile["Theta_turn"]
Theta_turn_sem = matFile["Theta_turn_sem"]
dPhi_turn = matFile["dPhi_turn"]
v_turn = matFile["v_turn"]
P4_turn_left = matFile["P4_turn_left"]
P4_turn_right = matFile["P4_turn_right"]

behavior_module = nwbfile.create_processing_module(name="behavior", description="Processed behavioral data")

task_module = nwbfile.create_processing_module(
    name="task",
    description="Task configuration and geometry"
)

analysis_module = nwbfile.create_processing_module(
    name="analysis",
    description="analysis derivatives"
)

# Create table
route_table = DynamicTable(
    name="instructed_routes",
    description="Instructed walking routes"
)

route_table.add_column(
    name="direction",
    description="Route identifier (e.g., left, right)"
)

route_table.add_column(
    name="x_coordinates",
    description="x coordinates in path coordinate frame (m)"
)

route_table.add_column(
    name="y_coordinates",
    description="y coordinates in path coordinate frame (m)"
)


route_table.add_row(
    direction="left",
    x_coordinates=left_route[:, 1],
    y_coordinates=left_route[:, 0]
)

route_table.add_row(
    direction="right",
    x_coordinates=right_route[:, 1],
    y_coordinates=right_route[:, 0]
)

print(route_table)
task_module.add(route_table)


subjectInfo = pd.DataFrame(
    {
        "SubjectID": ["R056", "R095", "R133", "R106", "R124"],
        "PaperSubjID": ["S1", "S2", "S3", "S4", "S5"],
        "Age": ["P36Y", "P45Y", "P24Y", "P39Y", "P30Y"],
        "Sex": ["M", "M", "F", "M", "F"],
        "Chan1": [
            "Left HP/HP",
            "Left HP/PRC",
            "Left HP/PRC",
            "Left Amy/HP",
            "Left HP/HP",
        ],
        "Chan2": ["Left HP/Sub", "Left PRC/PHC", "", "Left HP/HP", "Left HP/HP"],
        "Chan3": [
            "Right HP/HP",
            "Right PHC/Fs",
            "Right HP/PRC",
            "Right Tp/PRC",
            "Right HP/HP",
        ],
        "Chan4": ["Right HP/Sub", "", "Right PRC/PHC", "Right PRC/HP", "Right HP/PHC"],
    }
)

ecephys_module = nwbfile.create_processing_module(
        name="ecephys", description="Processed ephys data"
    )
fs = 250.0  # sampling frequency in Hz

iEEGdevice = nwbfile.create_device(
        name="iEEG_array",
        description="every participant had two depth electrode leads, each comprising four electrode contacts spaced at intervals of 10 mm."
        "We selected specific contacts in each individual on the basis of their location in the MTL to record from up to four bipolar channels "
        "in each participant. The localization of each of the two contacts forming a bipolar channel (chan 1 and 2) is "
        "specified for various MTL regions, including the hippocampus (HP), perirhinal cortex (PRC), parahippocampal cortex (PHC),"
        " subiculum (Sub), Fusiform gyrus (Fs), temporal pole (Tp) and amygdala (Amy)",
        manufacturer="Neuropace",
        model_number="320",
        model_name="RNS System",
    )


# -----------------------------
# Add custom electrode columns
# -----------------------------
# Add these once, before adding rows.
nwbfile.add_electrode_column(
    name="paper_subject_id",
    description="Participant ID used in the paper"
)

nwbfile.add_electrode_column(
    name="electrode_number",
    description="Electrode number within the file"
)

nwbfile.add_electrode_column(
    name="chan_number",
    description="Channel number within the participant (1-based)"
)

nwbfile.add_electrode_column(
    name="label",
    description="Label for the electrode, e.g. S4_Chan1"
)



# -----------------------------
# Create one ElectrodeGroup per subject
# -----------------------------
electrode_groups = {}

for _, row in subjectInfo.iterrows():
    paper_subj_id = row["PaperSubjID"]

    electrode_groups[paper_subj_id] = nwbfile.create_electrode_group(
        name=f"iEEG_group_{paper_subj_id}",
        description=(
            f"Electrode group for {paper_subj_id}. "
            "Medial temporal lobe iEEG contacts."
        ),
        device=iEEGdevice,
        location="Medial temporal lobe",
    )

# -----------------------------
# Populate the single electrodes table
# -----------------------------
# Keep track of which row indices belong to each subject
electrode_rows_by_subject = {sid: [] for sid in subjectInfo["PaperSubjID"]}

electrode_number = 0  # file-wide numbering

for _, row in subjectInfo.iterrows():
    paper_subj_id = row["PaperSubjID"]
    egroup = electrode_groups[paper_subj_id]

    for chan_num in range(1, 5):
        chan_key = f"Chan{chan_num}"
        loc_desc = row[chan_key]

        # Skip empty / blank channels
        if pd.isna(loc_desc):
            continue
        loc_desc = str(loc_desc).strip()
        if loc_desc == "":
            continue

        # Add a row to the NWB electrodes table
        # Required fields are: group and location
        nwbfile.add_electrode(
            id=electrode_number,  # explicit unique ID
            group=egroup,
            location=loc_desc,
            paper_subject_id=paper_subj_id,
            electrode_number=electrode_number,
            chan_number=chan_num,
            label=f"{paper_subj_id}_Chan{chan_num}",
        )

        # Row index in the table is the current length - 1
        row_index = len(nwbfile.electrodes) - 1
        electrode_rows_by_subject[paper_subj_id].append(row_index)

        electrode_number += 1

# -----------------------------
# Create S4-only subset region
# -----------------------------
s4_electrode_region = nwbfile.create_electrode_table_region(
    region=electrode_rows_by_subject["S4"],
    description="Electrodes for participant S4"
)


broadband_iEEG = ElectricalSeries(
            name="processed_broadband_iEEG",
            description="Exemplary broadband iEEG from S4 during real-world navigation (z score)",
            data=iEEG_expl,
            electrodes=s4_electrode_region,
            starting_time=0.0,  # timestamp of the first sample in seconds relative to the session start time
            rate=fs,  # in Hz

        )


theta_iEEG = ElectricalSeries(
            name="processed_theta_iEEG",
            description="Exemplary theta (4-12 Hz) iEEG from S4 during real-world navigation (z score)",
            data=Theta_expl,
            electrodes=s4_electrode_region,
            starting_time=0.0,  # timestamp of the first sample in seconds relative to the session start time
            rate=fs,  # in Hz

        )

ecephys_module.add(theta_iEEG)
ecephys_module.add(broadband_iEEG)


n_subjects = walks_left.shape[2]
assert walks_right.shape[2] == n_subjects

avg_walk_table = DynamicTable(
    name="average_walks",
    description="Average spatial walk per subject and route"
)

# Regular columns
avg_walk_table.add_column(
    name="subject_id",
    description="Subject identifier"
)

avg_walk_table.add_column(
    name="direction",
    description="Route label (left/right)"
)

# Ragged column: one Kx2 array per row
avg_walk_table.add_column(
    name="x_coordinates",
    description="Average spatial walk x coordinates in meters",
    index=True
)

avg_walk_table.add_column(
    name="y_coordinates",
    description="Average spatial walk y coordinates in meters",
    index=True
)

# Add rows
for i in range(n_subjects):

    left = walks_left[:,:,i]
    right = walks_right[:,:,i]
    avg_walk_table.add_row(
        subject_id=f"S{i+1}",
        direction="left",
        x_coordinates=left[:,1],
        y_coordinates=left[:,0]
    )
    avg_walk_table.add_row(
        subject_id=f"S{i+1}",
        direction="right",
        x_coordinates=right[:,1],
        y_coordinates=right[:,0]
    )


behavior_module.add(avg_walk_table)


f_axis = 2 ** np.arange(0, 7.0001, 0.1)
f_axis = f_axis[f_axis < 90]



tf_expl_l = np.asarray(TF_expl_L)
tf_expl_l = tf_expl_l[:, np.newaxis, :] # (6708, 1, 65)
# add decomposition series for the time/freq/power data for subj 4 - Fig 2
tfr = DecompositionSeries(
    name="wavelet_power_left_walks",
    description="Wavelet power at specific frequencies for left walks, participant S4",
    data=tf_expl_l,
    starting_time = 0.0,
    rate= fs,
    source_channels=s4_electrode_region, # need to specific channel 2
    #timestamps=t_power,
    metric="power",
    unit="uV^2"  # or appropriate unit
)

# Define spectral axis
for f in f_axis:
    tfr.add_band(
        band_name=f"{f} Hz",
        band_limits=(f, f),
        band_mean=f
    )

ecephys_module.add(tfr)


tf_expl_r = np.asarray(TF_expl_R)
tf_expl_r = tf_expl_r[:, np.newaxis, :]   # (6708, 1, 65)

trfr = DecompositionSeries(
    name="wavelet_power_right_walks",
    description="Wavelet power at specific frequencies for right walks, participant S4",
    data=tf_expl_r,
    starting_time = 0.0,
    rate= fs,
    source_channels=s4_electrode_region, # specify channel 2
    metric="power",
    unit="uV^2"  # or appropriate unit
)

# Define spectral axis
for f in f_axis:
    trfr.add_band(
        band_name=f"{f} Hz",
        band_limits=(f, f),
        band_mean=f
    )

ecephys_module.add(trfr)

# Fig 2c
# Create table
route_features_table = DynamicTable(
    name="walking_spatial_theta",
    description="Theta activity associated with walking route spatial coordinates"
)

route_features_table.add_column(
    name="direction",
    description="Route identifier (e.g., left, right)"
)

route_features_table.add_column(
    name="theta",
    description="Z-scored average theta activity associated with all participants' average walking route",
    index=True
)


route_features_table.add_row(
    direction="left",
    theta=avg_theta_HPC_L
)

route_features_table.add_row(
    direction="right",
    theta=avg_theta_HPC_R
)

analysis_module.add(route_features_table)
# time freq aligned with turns

tf_turn = np.asarray(TF_turn)[:, np.newaxis, :]

# add decomposition series for the time/freq/power data for subj 4 - Fig 2
turn_tf = DecompositionSeries(
    name="time_freq_turns",
    description="Average time frequency aligned with all turns across participants",
    data=tf_turn,
    starting_time = -3.0,
    rate = fs,
    metric="power",
    unit="z"  # or appropriate unit
)

# Define spectral axis
for f in f_axis:
    turn_tf.add_band(
        band_name=f"{f} Hz",
        band_limits=(f, f),
        band_mean=f
    )

ecephys_module.add(turn_tf)

# mean theta activity +/- standard error
avgTheta_turns = TimeSeries(
    name="avg_theta_turns",
    description="Average theta activity aligned with all turns across participants",
    data=Theta_turn,
    starting_time = -3.0,
    rate = fs,
    unit = "Z"
)

ecephys_module.add(avgTheta_turns)

# mean theta activity +/- standard error
avgTheta_turns_sem = TimeSeries(
    name="avg_theta_turns_sem",
    description="Average theta activity aligned with all turns across participants",
    data=Theta_turn_sem,
    starting_time = -3.0,
    rate = fs,
    unit = "Z"
)

ecephys_module.add(avgTheta_turns_sem)

# mean speed of hips aligned to turns
hip_speed = TimeSeries(
    name="hip_speed_turns",
    description="Mean speed of hips aligned with all turns across participants",
    data=v_turn,
    starting_time = 0.0,
    rate = fs,
    unit = "m/s^2"
)

# mean angular velocity of hips aligned to turns

hip_angular_velocity = TimeSeries(
    name="hip_angular_velocity_turns",
    description="Mean angular velocity of hips aligned with all turns across participants",
    data=dPhi_turn,
    starting_time = 0.0,
    rate = fs,
    unit="degrees/s"
)


speed_behavioral_ts = BehavioralTimeSeries(time_series=hip_speed, name="hip_speed")
angular_velocity_behavioral_ts = BehavioralTimeSeries(time_series=hip_angular_velocity, name="hip_angular_velocity")

behavior_module.add(speed_behavioral_ts)
behavior_module.add(angular_velocity_behavioral_ts)


# third matfile

filepath = os.path.join(folder, 'data_3.mat')
matFile = loadmat(filepath)

# real and imagined theta on top of spatial walks
HPC_L2D = matFile["HPC_L2D"] # in z, 7793 x 2
HPC_R2D = matFile["HPC_R2D"] # in z, 7340 x 2

# Create table
walk_theta_table = DynamicTable(
    name="walk_theta",
    description="Theta for real and imagined walks aligned to average spatial coordinates of left and right walks"
)

walk_theta_table.add_column(
    name="walk_type",
    description="Type of walk (real or imagined)"
)


walk_theta_table.add_column(
    name="direction",
    description="left or right route"
)

walk_theta_table.add_column(
    name="theta",
    description="Z score theta",
    index=True
)


walk_theta_table.add_row(
    walk_type = "real",
    direction = "left",
    theta= HPC_L2D[:,0]
)

walk_theta_table.add_row(
    walk_type = "imagined",
    direction = "left",
    theta= HPC_L2D[:,1]
)

walk_theta_table.add_row(
    walk_type = "real",
    direction = "right",
    theta= HPC_R2D[:,0]
)

walk_theta_table.add_row(
    walk_type = "imagined",
    direction = "right",
    theta= HPC_R2D[:,1]
)

analysis_module.add(walk_theta_table)

# theta trials for P4
theta_trials = matFile["Theta_trials"] # in z,


p4_theta_trials_series = TimeSeries(
    name="P4_theta_trials",
    description="Theta activity for all 35 individual trials for participant S4",
    data=theta_trials,
    starting_time=0.0,
    rate = fs,
    unit = "Z"
)

ecephys_module.add(p4_theta_trials_series)

# temporal consistency
cnsty_grp = matFile["cnsty_grp"] #


#  Create table
corr_theta_table = DynamicTable(
    name="corr_theta",
    description="Correlation between the mean theta signals from different halves of participants' trials fo control, imagined, and real walks"
)

corr_theta_table.add_column(
    name="condition",
    description="Condition label (control, imagined, real)"
)

corr_theta_table.add_column(
    name="correlation",
    description="correlation value for each electrode in the experiment (across all participants) (18 x 1)"
)


corr_theta_table.add_row(
    condition = "control",
    correlation = cnsty_grp[:,0]
)

corr_theta_table.add_row(
    condition = "imagined",
    correlation = cnsty_grp[:,1]
)

corr_theta_table.add_row(
    condition = "real",
    correlation = cnsty_grp[:,2]
)

analysis_module.add(corr_theta_table)

filepath = os.path.join(folder, 'data_4.mat')
matFile = loadmat(filepath)

route_mdl_R = matFile["route_mdl_R"] # right
route_mdl_L = matFile["route_mdl_L"] # left

Walk_recon_R = matFile["Walk_recon_R"] # right
Walk_recon_L = matFile["Walk_recon_L"] # left

Imag_recon_R = matFile["Imag_recon_R"] # right
Imag_recon_L = matFile["Imag_recon_L"] # left

walk_pos_Lw = matFile["Walk_pos_Lw"]
walk_pos_Rw = matFile["Walk_pos_Rw"]
imag_pos_Lw = matFile["Imag_pos_Lw"]
imag_pos_Rw = matFile["Imag_pos_Rw"]





route_models = DynamicTable(
    name="route_models",
    description="-sine and cosine route models for left and right walks for reconstructed real and imagined walks"
)

route_models.add_column(
    name="condition",
    description="Condition label  (baseline_model, imagined, real)"
)

route_models.add_column(
    name="model_type",
    description="Type of route model (-sine, cosine)"
)

route_models.add_column(
    name="direction",
    description="Direction of route model (left, right)"
)

route_models.add_column(
    name="theta_reconstruction",
    description="theta recontsructions during the walkling routes (Z)",
    index = True
)

route_models.add_row(
    condition = "baseline_model",
    model_type = "-sine",
    direction = "left",
    theta_reconstruction = route_mdl_L[:,1]
)

route_models.add_row(
    condition = "baseline_model",
    model_type = "cosine",
    direction = "left",
    theta_reconstruction = route_mdl_L[:,0]
)

route_models.add_row(
    condition = "baseline_model",
    model_type = "-sine",
    direction = "right",
    theta_reconstruction = route_mdl_R[:,1]
)

route_models.add_row(
    condition = "baseline_model",
    model_type = "cosine",
    direction = "right",
    theta_reconstruction = route_mdl_R[:,0]
)

# -- real walks reconstruction -- #

route_models.add_row(
    condition = "real",
    model_type = "-sine",
    direction = "left",
    theta_reconstruction = Walk_recon_L[:,1]
)

route_models.add_row(
    condition = "real",
    model_type = "cosine",
    direction = "left",
    theta_reconstruction = Walk_recon_L[:,0]
)

route_models.add_row(
    condition = "real",
    model_type = "-sine",
    direction = "right",
    theta_reconstruction = Walk_recon_R[:,1]
)

route_models.add_row(
    condition = "real",
    model_type = "cosine",
    direction = "right",
    theta_reconstruction = Walk_recon_R[:,0]
)

# -- imagined walks reconstruction -- #

route_models.add_row(
    condition = "imagined",
    model_type = "-sine",
    direction = "left",
    theta_reconstruction = Imag_recon_L[:,1]
)

route_models.add_row(
    condition = "imagined",
    model_type = "cosine",
    direction = "left",
    theta_reconstruction = Imag_recon_L[:,0]
)

route_models.add_row(
    condition = "imagined",
    model_type = "-sine",
    direction = "right",
    theta_reconstruction = Imag_recon_R[:,1]
)

route_models.add_row(
    condition = "imagined",
    model_type = "cosine",
    direction = "right",
    theta_reconstruction = Imag_recon_R[:,0]
)

analysis_module.add(route_models)


reconstructed_route_reps = DynamicTable(
    name="reconstructed_route_rep",
    description="Reconstructed route representations of real-world and imagined navigation. Each data point represents data averaged over 0.5-s time bins, derived from data pooled across all channels."
)

reconstructed_route_reps.add_column(
    name="condition",
    description="Condition label  (control, imagined, real)"
)

reconstructed_route_reps.add_column(
    name="model_type",
    description="Type of route model (-sine, cosine)"
)

reconstructed_route_reps.add_column(
    name="direction",
    description="Direction of route model (left, right)"
)

reconstructed_route_reps.add_column(
    name="route_reconstruction",
    description="reconstructed route representations using 0.5-s time bins of theta (Z)",
    index = True
)

reconstructed_route_reps.add_row(
    condition = "real",
    model_type = "-sine",
    direction = "left",
    route_reconstruction = walk_pos_Lw[:,1]
)

reconstructed_route_reps.add_row(
    condition = "real",
    model_type = "-sine",
    direction = "right",
    route_reconstruction = walk_pos_Rw[:,1]
)

reconstructed_route_reps.add_row(
    condition = "real",
    model_type = "cosine",
    direction = "left",
    route_reconstruction = walk_pos_Lw[:,0]
)

reconstructed_route_reps.add_row(
    condition = "real",
    model_type = "cosine",
    direction = "right",
    route_reconstruction = walk_pos_Rw[:,0]
)

# imageind reconstructed route representations

reconstructed_route_reps.add_row(
    condition = "imagined",
    model_type = "-sine",
    direction = "left",
    route_reconstruction = imag_pos_Lw[:,1]
)

reconstructed_route_reps.add_row(
    condition = "imagined",
    model_type = "-sine",
    direction = "right",
    route_reconstruction = imag_pos_Rw[:,1]
)

reconstructed_route_reps.add_row(
    condition = "imagined",
    model_type = "cosine",
    direction = "left",
    route_reconstruction = imag_pos_Lw[:,0]
)

reconstructed_route_reps.add_row(
    condition = "imagined",
    model_type = "cosine",
    direction = "right",
    route_reconstruction = imag_pos_Rw[:,0]
)


# control condition


ctrl_pos_Lw = matFile["Ctrl_pos_Lw"]
ctrl_pos_Rw = matFile["Ctrl_pos_Rw"]


reconstructed_route_reps.add_row(
    condition = "control",
    model_type = "-sine",
    direction = "left",
    route_reconstruction = ctrl_pos_Lw[:,1]
)

reconstructed_route_reps.add_row(
    condition = "control",
    model_type = "-sine",
    direction = "right",
    route_reconstruction = ctrl_pos_Rw[:,1]
)

reconstructed_route_reps.add_row(
    condition = "control",
    model_type = "cosine",
    direction = "left",
    route_reconstruction = ctrl_pos_Lw[:,0]
)

reconstructed_route_reps.add_row(
    condition = "control",
    model_type = "cosine",
    direction = "right",
    route_reconstruction = ctrl_pos_Rw[:,0]
)

# baseline models
route_mdl_Lw = matFile["route_mdl_Lw"]
route_mdl_Rw = matFile["route_mdl_Rw"]


reconstructed_route_reps.add_row(
    condition = "baseline_model",
    model_type = "-sine",
    direction = "left",
    route_reconstruction = route_mdl_Lw[:,1]
)

reconstructed_route_reps.add_row(
    condition = "baseline_model",
    model_type = "-sine",
    direction = "right",
    route_reconstruction = route_mdl_Rw[:,1]
)

reconstructed_route_reps.add_row(
    condition = "baseline_model",
    model_type = "cosine",
    direction = "left",
    route_reconstruction = route_mdl_Lw[:,0]
)

reconstructed_route_reps.add_row(
    condition = "baseline_model",
    model_type = "cosine",
    direction = "right",
    route_reconstruction = route_mdl_Rw[:,0]
)


analysis_module.add(reconstructed_route_reps)

N_seg = matFile["N_seg"][0,0]

nwbfile.add_scratch(
    int(N_seg),
    name="n_seg",
    description="number of segments",
)





# theta seg



rel_pos_theta_table = DynamicTable(
    name="rel_pos_theta",
    description="Theta activity for each segment of the route"
)

# data
seg_ax = np.asarray(matFile["seg_ax"]).squeeze()        # shape: (181,)
theta_seg = np.asarray(matFile["Theta_seg"])            # shape: (181, 18)

# first column
rel_pos_theta_table.add_column(
    name="segment_position",
    description="Relative position along the segmented route (0 to 2pi)"
)

# get electrode labels
electrode_labels = list(nwbfile.electrodes["label"][:theta_seg.shape[1]])

# one column per electrode
for label in electrode_labels:
    rel_pos_theta_table.add_column(
        name=f"theta_{label}",
        description=f"Theta activity (z) for electrode {label}"
    )

# add one row per segment
for r in range(len(seg_ax)):
    row_dict = {
        "segment_position": float(seg_ax[r])
    }

    for c, label in enumerate(electrode_labels):
        row_dict[f"theta_{label}"] = float(theta_seg[r, c])

    rel_pos_theta_table.add_row(**row_dict)

analysis_module.add(rel_pos_theta_table)


# probabilities actual vs estimated position
lin_ax = np.asarray(matFile["lin_ax"]).squeeze()
H2D_imag = np.asarray(matFile["H2D_imag"])
H2D_ctrl = np.asarray(matFile["H2D_ctrl"])
H2D_walk = np.asarray(matFile["H2D_walk"])

prob_map_table = DynamicTable(
    name="route_probability_maps",
    description="2D route-position probability maps stored row-wise by condition"
)


prob_map_table.add_column(
    name="lin_ax",
    description="Route position in percent from 0 to 100, shared by rows and columns"
)

prob_map_table.add_column(
    name="H2D_imag",
    description="2D probability map for imagined walks, rows and columns corresopnd to lin_ax",
    index=True
)

prob_map_table.add_column(
    name="H2D_ctrl",
    description="2D probability map for control walks, rows and columns corresopnd to lin_ax",
    index=True
)

prob_map_table.add_column(
    name="H2D_walk",
    description="2D probability map for walked routes, rows and columns corresopnd to lin_ax",
    index=True
)

prob_map_table.add_row(
    lin_ax=lin_ax,
    H2D_imag=H2D_imag,
    H2D_ctrl=H2D_ctrl,
    H2D_walk=H2D_walk
)

analysis_module.add(prob_map_table)

# error histograms

ph_ax = np.asarray(matFile["ph_ax"]).squeeze()

err_walk = np.asarray(matFile["err_walk"]).squeeze()
err_imag = np.asarray(matFile["err_imag"]).squeeze()
err_ctrl = np.asarray(matFile["err_ctrl"]).squeeze()

n_left = 7327
n_right = 7748
n_total = n_left + n_right


err_walk_left = err_walk[:n_left]
err_walk_right = err_walk[n_left:]
err_imag_left = err_imag[:n_left]
err_imag_right = err_imag[n_left:]
err_ctrl_left = err_ctrl[:n_left]
err_ctrl_right = err_ctrl[n_left:]


def complex_to_2columns(arr):
    arr_2col = np.stack((np.real(arr), np.imag(arr)), axis=-1)
    return arr_2col

circular_error_table = DynamicTable(
    name="circular_reconstruction_error",
    description=(
        "Complex-valued circular reconstruction error data with shared circular axis. first number is real part, second number is imaginary part. "
        "The ph_ax vector defines the circular histogram axis in radians."
    )
)

circular_error_table.add_column(
    name="ph_ax",
    description="Circular histogram bin edges in radians, approximately spanning -3 to 3",
    index=True
)

circular_error_table.add_column(
    name="err_walk_left",
    description="Complex circular reconstruction error values for walking condition, left routes stored as Nx2, where first column is real part and second column is the imaginary part",
    index=True
)

circular_error_table.add_column(
    name="err_walk_right",
    description="Complex circular reconstruction error values for walking condition, right routes stored as Nx2, where first column is real part and second column is the imaginary part",
    index=True
)

circular_error_table.add_column(
    name="err_imag_left",
    description="Complex circular reconstruction error values for imagined condition, left routes",
    index=True
)

circular_error_table.add_column(
    name="err_imag_right",
    description="Complex circular reconstruction error values for imagined condition, right routes",
    index=True
)

circular_error_table.add_column(
    name="err_ctrl_left",
    description="Complex circular reconstruction error values for control condition, left routes",
    index=True
)

circular_error_table.add_column(
    name="err_ctrl_right",
    description="Complex circular reconstruction error values for control condition, right routes",
    index=True
)

# Add one row: store complex data as real+imag paired columns
circular_error_table.add_row(
    ph_ax=ph_ax,
    err_walk_left=complex_to_2columns(err_walk_left),
    err_walk_right=complex_to_2columns(err_walk_right),
    err_imag_left=complex_to_2columns(err_imag_left),
    err_imag_right=complex_to_2columns(err_imag_right),
    err_ctrl_left=complex_to_2columns(err_ctrl_left),
    err_ctrl_right=complex_to_2columns(err_ctrl_right)
)


analysis_module.add(circular_error_table)

## ----- Save NWB ----- ##
# Get the default backend configuration
backend_configuration = get_default_backend_configuration(nwbfile, backend="hdf5")



# Apply gzip compression with zstd compressor to all datasets
backend_configuration.apply_global_compression(
    compression_method="gzip",
    compression_options={
        "compression_opts": 4  # gzip levels 1-9
    },
)

os.makedirs(saveNWBFolder, exist_ok=True)
nwbfile_path = os.path.join(saveNWBFolder, "Zenodo_compressed_groupSubject.nwb")

configure_and_write_nwbfile(
    nwbfile, nwbfile_path=nwbfile_path, backend_configuration=backend_configuration
)
