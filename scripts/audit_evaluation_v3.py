"""Audit an existing temporal_v3 result bundle without recomputing models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation.audit import audit_result_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()
    result = audit_result_bundle(args.result_dir)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
