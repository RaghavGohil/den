import argparse
from ..parser.note import backend


def execute(args: argparse.Namespace) -> None:
    """
    Add a note for the current project.
    """
    content = ""
    reference = None
    
    if hasattr(args, "note") and args.note:
        content = " ".join(args.note).strip()
    
    if hasattr(args, "ref") and args.ref:
        try:
            from pathlib import Path
            filepath, lines = args.ref.split(":", 1)
            start_str, end_str = lines.split(",", 1)
            start_line = int(start_str)
            end_line = int(end_str)

            abs_filepath = Path(filepath).resolve()
            if abs_filepath.exists():
                reference = {
                    "filepath": str(filepath),
                    "start_line": start_line,
                    "end_line": end_line,
                }
        except Exception:
            pass

    if not content:
        print("Empty note, skipped.")
        return

    try:
        backend.add_note(content, reference)
    except ValueError as e:
        print(e)
    except Exception as e:
        print(f"Error adding note: {e}")
