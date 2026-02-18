from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tmp-file", required=True)
    parser.add_argument("--mode", choices=["fail", "cleanup"], required=True)
    parser.add_argument("--failed-step", default="")
    parser.add_argument("--error-type", default="")
    parser.add_argument("--error-message", default="")
    args = parser.parse_args()

    tmp_path = Path(args.tmp_file)

    if args.mode == "fail":
        tmp_path.write_text("intermediate artifact\n", encoding="utf-8")
        print(f"Created temporary file: {tmp_path}")
        print("Simulating failure after creating intermediate artifact")
        return 2

    if tmp_path.exists():
        tmp_path.unlink()
        print(f"Cleanup removed temporary file: {tmp_path}")
    else:
        print(f"Cleanup: no temporary file found at {tmp_path}")

    print(f"Recovery context step={args.failed_step}")
    print(f"Recovery context type={args.error_type}")
    print(f"Recovery context message={args.error_message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
