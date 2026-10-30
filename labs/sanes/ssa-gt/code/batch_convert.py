#!/usr/bin/env python3
"""Batch driver for the Sanes SSA GT experiment-to-NWB conversion.

Discovers every ``experiment_*`` directory directly under ``--input`` or one
folder below it, and converts each into ``sub-multi/sub-multi_ses-experiment<ID>_behavior.nwb``
plus one ``sub-<NN>/sub-<NN>_ses-experiment<ID>.nwb`` per tracked animal.
Experiments whose multisubject file already exists are skipped unless
``--overwrite`` is given.

Experiments are converted one at a time, since each one stages its whole
concatenated audio on disk next to the output.
"""

import argparse
import sys
from pathlib import Path

# The project directory is "ssa-gt", and a hyphen cannot appear in a Python
# package name, so the sibling module is imported by name from this file's
# own directory instead (Suthana in-lab and Zhang precedent).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _sanes_ssa_gt_to_nwb import build_nwb  # noqa: E402


def discover_experiments(incoming_dir, /):
    candidates = [*incoming_dir.glob("experiment_*"), *incoming_dir.glob("*/experiment_*")]
    experiments = sorted(path for path in candidates if path.is_dir())
    return experiments


def convert_batch(*, incoming_dir, standardized_dir, config_path, overwrite=False):
    experiments = discover_experiments(incoming_dir)
    if not experiments:
        print(f"No experiment_* directories found under {incoming_dir}")
        return 0
    for experiment in experiments:
        label = experiment.name.removeprefix("experiment_")
        session = f"experiment{label}"
        output_path = standardized_dir / "sub-multi" / f"sub-multi_ses-{session}_behavior.nwb"
        if output_path.exists() and not overwrite:
            print(f"Exists, skipping (use --overwrite): {output_path}")
            continue
        print(f"Converting {experiment} -> {output_path}")
        build_nwb(experiment_dir=experiment, output_path=output_path, config_path=config_path)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", dest="input_dir", type=Path, required=True)
    parser.add_argument("--output", dest="output_dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    return convert_batch(
        incoming_dir=args.input_dir, standardized_dir=args.output_dir, config_path=args.config, overwrite=args.overwrite
    )


if __name__ == "__main__":
    raise SystemExit(main())
