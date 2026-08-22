## Overview

This is the data conversion from Inman team (R61MH135109). The experiment was a navigation task where participants were instructed to navigate through the Campus in a specific route. Each participant went through 6 to 8 walks. Each original .mat file contains data from one walk.

### Data Organization
- d_[variable name] -> Data Values for each time point
- ntp_[variable name]  -> NTP time stamp for each sample within the d_[variable name]
- fs_[variable name] -> Sampling rate for signals
- fr_[variable name] -> Frame Rate for videos
- offset_[variable name] -> defined as offset time for synchronization and is defined only for some of the variables
- evnts_tbl -> It is a table variable that includes annotations made by RAs to identify different events that were happened during the walk. The time of each event is specified in different formats: PupilFrame (Frame number in the video of the Pupil Lab Eye-tracking Device), GoProGrame (Frame number in the video captured by GoPro Camera), NPSample (Corresponding sample index in the neural data), NTP (NTP time stamp).

*Extra Details:*
Note that d_[variable name] and ntp_[variable name] are mostly 1D array of the same size and their size is the number of samples that were recorded across the whole walk. So for a variable if the length is L_[variable] then L_[variable]/fs_[variable] gives the duration of the recording in seconds for variable. Note that the not all variables were recorded for the whole walk. There are variables that are empty or they have been recorded only for a portion of the walk. Though, the recorded samples can be synchronized by the ntp_[variable name] with other variables.

### Variable Names:
- amb: Ambient light (1D Array of doubles)
- gaze_fix: Fixation or not (1D Array of binary values)
- gaze_x: Horizontal Coordinate of the gaze points in the Eye-tracking Video (1D Array of doubles)
- gaze_y: Vertical Coordinate of the gaze points in the Eye-tracking Video (1D Array of doubles)
- imu: IMU data including gyro (angular velocity) in X, Y, and Z, acceleration in X, Y, and Z, roll, and pitch (struct of 1D arrays)
- np: 4 channels of Neural recordings, intracranial EEG (2D Array with 4 columns corresponding to iEEG channels)
- xs: walking pace or movement velocity (1D Array of doubles)

### MATLAB File Conversion for Reading into Python
To read the data properly from .mat into python, there are a couple steps you have to do within MATLAB to reformat the file structure. Basically, MATLAB table formats are not easily read into python. So, we need to convert the table to a struct to be readable. We also resave that file with the -v7.3 flag for HDF5.

```
s = load('your_data.mat');
s.evnts_struct = table2struct(s.evnts_tbl);
save('your_data.mat','-struct','s','-v7.3');
```

### Folder and File Structure

```
sub-XYZ/
└── ses-YYYYMMDD/
    └── sub-XYZ_ses-YYYYMMDD_behavior+ecephys.nwb
        ├── session_start_time
        ├── session_description
        ├── general
        │   └── subject
        ├── acquisition
        │   ├── behavior
        │   │   ├── ambient_light        ← d_amb (TimeSeries)
        │   │   ├── eye_tracking (EyeTracking)
        │   │   │   ├── gaze_xy          ← d_gaze_x + d_gaze_y (SpatialSeries)
        │   │   │   └── gaze_fix         ← d_gaze_fix (TimeSeries)
        │   │   ├── imu_gyro             ← d_imu (gyro x, y,z) (TimeSeries)
        │   │   ├── imu_accel            ← d_imu (acceleration x, y,z) (TimeSeries)
        │   │   ├── imu_orientation      ← d_imu (roll, pitch) (SpatialSeries)
        │   │   ├── kde                  ← d_kde (TimeSeries)
        │   │   └── xs                   ← d_xs (TimeSeries)
        │   └── ecephys
        │       ├── Electrodes table, device
        │       └── ieeg_raw             ← d_np (ElectricalSeries)
        ├── processing
        │   └── behavior
        │       └── events               ← events_tbl (DynamicTable)
        └── metadata/

```

### Notes

The script 'inman_to_nwb.py' converts one session into one NWB file. The wrapper 'batch_convert.py' calls it for every `.mat` file found under an incoming directory and creates the subject/ NWB naming structure above, with two DANDI-required deviations from the tree sketch. The session label is `ses-walk<N>` (per-walk dates are not yet available in the metadata config), and each NWB sits directly under `sub-XYZ/` rather than in a `ses-` subfolder (dandi validation rejects nested session folders).
