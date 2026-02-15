from __future__ import annotations

import argparse

from .engine import WorkflowEngine
from .ui import App


def main() -> None:
    parser = argparse.ArgumentParser(description="YAML CLI UI")
    parser.add_argument("yaml", help="Path to workflow yaml")
    args = parser.parse_args()

    engine = WorkflowEngine.from_file(args.yaml)
    app = App(engine, args.yaml)
    app.mainloop()


if __name__ == "__main__":
    main()
