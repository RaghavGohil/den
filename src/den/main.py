"""
Den - Context management for projects made easy.
"""

import sys
import traceback

from . import cmd
from .utils.platform import check_platform_support


def main() -> None:
    try:
        check_platform_support()
        cmd.execute()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        print("If this is a significant issue, please report this on GitHub.")
        sys.exit(1)


if __name__ == "__main__":
    main()
