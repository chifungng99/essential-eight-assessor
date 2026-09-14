"""Lets the tool run straight from a clone: `python3 -m e8`, nothing installed."""

import sys

from e8.cli import main

if __name__ == "__main__":
    sys.exit(main())
