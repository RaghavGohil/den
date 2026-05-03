import os
import tempfile
import subprocess
import argparse

from ..utils import colors
from .note import backend
from . import notes_helper


def execute(args: argparse.Namespace) -> None:
    """
    Edit a note by its display index or hash ID using $EDITOR.
    """
    notes = backend.load_notes()

    if not notes:
        print("No notes to edit.")
        return

    idx = backend.find_note_index(args.id)

    if idx == -1:
        if args.id:
            print(f"Could not find note with ID: {args.id}")
        else:
            print("No notes to edit.")
        return

    n = notes[idx]
    editor_text = notes_helper.format_editor_content(n)
    editor = os.environ.get("EDITOR", "nano")

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", prefix="den_edit_", delete=False
        ) as tmp:
            tmp.write(editor_text)
            tmp_path = tmp.name

        subprocess.run([editor, tmp_path], check=True)

        with open(tmp_path, "r") as f:
            raw = f.read()

    except subprocess.CalledProcessError:
        print("Editor exited with an error.")
        return
    except OSError as e:
        print(f"Unable to open editor: {e}")
        return
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    new_content = notes_helper.parse_editor_content(raw)

    if new_content == n.get("content", ""):
        print(colors.dim("No changes made."))
        return

    updated = backend.edit_note(args.id, new_content)

    if updated:
        print(
            f"{colors.green('Updated:')} {new_content[:50]}{'...' if len(new_content) > 50 else ''}"
        )
