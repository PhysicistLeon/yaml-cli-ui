from __future__ import annotations

import argparse

from yaml_cli_ui.ui import run_ui


def main() -> None:
    parser = argparse.ArgumentParser(description="YAML-driven CLI pipeline UI")
    parser.add_argument("yaml", help="Path to workflow YAML file")
    args = parser.parse_args()
    run_ui(args.yaml)


if __name__ == "__main__":
    main()
