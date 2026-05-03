import argparse

from ..parser.note import backend
from ..utils import colors


def execute(args: argparse.Namespace) -> None:
    """
    Remove a note by its display index or hash ID.
    """
    removed = backend.remove_note(args.id)

    if removed:
        content = removed.get("content", "")
        preview = content[:50] + "..." if len(content) > 50 else content
        print(f"{colors.red('Removed:')} {preview}")
    else:
        if args.id:
            print(f"Could not find note with ID: {args.id}")
        else:
            print("No notes to remove.")
