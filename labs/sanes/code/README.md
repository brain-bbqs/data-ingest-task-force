<!-- Original conversion notes written by Neha Thomas (neha-thomas477), ported
verbatim from the original conversion work. The text below is unchanged, including
the section headings the original left empty. See ../README.md for how the lab is
wired into this repository, and for the operational notes on running the port. -->

## Overview


### Data Organization


### Variable Names:


### Folder and File Structure
```
sub-XYZ/
└── ses-YYYYMMDD/
    └── sub-XYZ_ses-YYYYMMDD.nwb
        ├── session_start_time
        ├── session_description
        ├── general
        │   └── subject
        ├── SLEAP_pose_estimation (SLEAPInterface)
        ├── acquisition
        │   ├── acoustic_waveform (TimeSeries)
        │   └── external_behavioral_videos (ImageSeries)
        └── behavioral
            └── vocalizations_table (TimeIntervals)
```