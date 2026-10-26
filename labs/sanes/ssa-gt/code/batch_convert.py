#!/usr/bin/env python3
"""Batch driver for the Sanes SSA GT experiment-to-NWB conversion."""

import argparse
from pathlib import Path

try:
    from ._sanes_ssa_gt_to_nwb import build_nwb
except ImportError:
    from _sanes_ssa_gt_to_nwb import build_nwb


def convert_batch(*, incoming_dir, standardized_dir, config_path, overwrite=False):
    experiments = sorted(incoming_dir.glob("experiment_*"))
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
    return convert_batch(incoming_dir=args.input_dir, standardized_dir=args.output_dir, config_path=args.config, overwrite=args.overwrite)


if __name__ == "__main__":
    raise SystemExit(main())
