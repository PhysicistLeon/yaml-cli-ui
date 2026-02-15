import argparse

from yaml_cli_ui.ui import launch


def main() -> None:
    parser = argparse.ArgumentParser(description="Dynamic YAML CLI pipeline UI")
    parser.add_argument("config", help="Path to YAML config")
    args = parser.parse_args()
    launch(args.config)


if __name__ == "__main__":
    main()
