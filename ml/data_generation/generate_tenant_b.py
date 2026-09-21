"""Generate and load pilot tenant B (tenant-b).

    python ml/data_generation/generate_tenant_b.py --reset
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ml.data_generation.generator import PILOT_TENANTS, generate_tenant
from ml.data_generation.load_to_db import load_tenant

SLUG = "tenant-b"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument(
        "--dry-run", action="store_true", help="Generate and report without loading"
    )
    args = parser.parse_args()

    spec = PILOT_TENANTS[SLUG]
    data = generate_tenant(spec)

    if args.dry_run:
        print(f"{SLUG} ({spec.name}) target Level {spec.target_level}")
        for key, value in data.summary().items():
            print(f"    {key:22} {value:>8,}")
        return

    result = load_tenant(data, reset=args.reset)
    print(
        f"{SLUG}: Level {result['level']} (expected {spec.target_level}), "
        f"score {result['score']:.1f}"
    )


if __name__ == "__main__":
    main()
