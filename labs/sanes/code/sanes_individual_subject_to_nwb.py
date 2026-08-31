# Original conversion script developed by Neha Thomas (neha-thomas477), committed
# verbatim as provenance. This is one of the v2 scripts that supersede the v1
# notebook (sanesDatatoNWB_v2.ipynb, retired from the tree; see git history and
# ../README.md) this repository originally ported. It is a later/rougher pass
# that tries to attach a Subject to an already-exported per-track NWB file by
# guessing the track index from a processing-module name; ../README.md explains
# why its intent is treated as subsumed by concat_sanes_data.py writing
# subject= directly, and documents the bugs left as-is here (see "Known rough
# edges"). It is kept for historical/exploratory provenance only, the same
# treatment pynaViz_ex.py got for v1, and is not run by the batch driver.

import re
import sys
import os
from pynwb import NWBFile, NWBHDF5IO
from pynwb.image import ImageSeries

from pathlib import Path
from dateutil.tz import tzlocal
from datetime import datetime
import argparse
from pynwb.file import Subject

import sleap_io as sio

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
        "--inputFolder", required=True, type=Path, help="Path to single animal sleap nwb files"
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


def build_nwb(out_nwb, cfg):
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
    nwbfile = NWBFile(
        session_description=config.cfg_get(
            "session", "description", CFG=cfg
        ),  # hardcode what session is/information in this block
        identifier="Sanes-Multisubject-1",
        session_start_time=session_start,
        experimenter=config.cfg_get("session", "experimenter", CFG=cfg),
        institution=config.cfg_get("session", "instituition", CFG=cfg),
    )

    nwb_subject = Subject(
        subject_id=config.cfg_get("subject_0", "id", CFG=cfg),
        species=config.cfg_get("subject_0", "species", CFG=cfg),
        age=config.cfg_get("subject_0", "age", CFG=cfg),
        sex=config.cfg_get("subject_0", "sex", CFG=cfg),
    )
    
    nwbfile.subject = nwb_subject

    # get subject info from config file
    # subject definition
    # subject_id = subject_name
    # species = config.cfg_get("subject", "species", CFG=cfg)
    # age = config.cfg_get("subject", "age", CFG=cfg)
    # sex = config.cfg_get("subject", "sex", CFG=cfg)
    # description_subject = config.cfg_get("subject", "description", CFG=cfg)


def main():
    # usage
    args = parse_args()

    cfg = config.load_cfg(args.config)


    in_path = args.inputFolder
    # get existing nwb files 

    for nwb_file in in_path.parent.glob("*.nwb"):
    


        #input_nwb = Path("existing_sleap_file.nwb")
        output_nwb = Path(f"{nwb_file.stem}_with_subject.nwb")

    with NWBHDF5IO(str(nwb_file), "r") as io:
        nwbfile = io.read()
        # get track index number from inside processing 


        for module_name, module in nwbfile.processing.items():
            print(f"Processing module: {module_name}")

        for obj_name, obj in module.data_interfaces.items():
            print(f"  Object name: {obj_name}")
            print(f"  Object type: {type(obj)}")

            match = re.search(r"track[_=](\d+)", obj_name)
            if match:
                track_index = int(match.group(1))
                subject_id = f"subject_{track_index}"

                print(f"  track index: {track_index}")
                print(f"  matched subject id: {subject_id}")

        nwbfile.subject = Subject(
            subject_id=config.cfg_get(subject_id, "id", CFG=cfg),
        species=config.cfg_get(subject_id, "species", CFG=cfg),
        age=config.cfg_get(subject_id, "age", CFG=cfg),
        sex=config.cfg_get(subject_id, "sex", CFG=cfg),
        )

        with NWBHDF5IO(str(output_nwb), "w") as export_io:
            export_io.export(src_io=io, nwbfile=nwbfile)
        #build_nwb(out_nwb=out_path, cfg=cfg)


if __name__ == "__main__":
    """
    Example CLI usage
    --------
    python sanes_multisubject_to_nwb.py --inputFolder exampleData/ --config ./config_multisubject.yaml --out ./Sanes-S01-MultiSubject.nwb
    """
    print("calling main")

    main()
