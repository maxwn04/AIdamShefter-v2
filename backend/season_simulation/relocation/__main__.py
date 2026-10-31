"""Set offline library behavior before importing application composition."""

import importlib
import os


def main() -> None:
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    importlib.import_module("backend.season_simulation.relocation.service").main()


if __name__ == "__main__":
    main()
