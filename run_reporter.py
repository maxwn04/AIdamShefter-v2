#!/usr/bin/env python3
"""Entry point for the reporter CLI.

This script sets up the Python path correctly before running the reporter.
"""

import sys
from pathlib import Path

# Add project root and reporter/src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "reporter" / "src"))

# Now import and run
from app.runner import main

if __name__ == "__main__":
    main()
