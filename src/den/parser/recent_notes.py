import os
import json
import shutil
import argparse
from datetime import datetime

from .. import config
from ..utils import colors
from .notes_helper import format_note_context


def _load_all_notes() -> list[dict]:
    """
    Load notes from all known projects.
    Returns a list of notes with an added 'project_path' key.
    """
    projects_file = os.path.join(config.config.DATA_DIR_PATH, "projects.json")
    if not os.path.exists(projects_file):
        return []

    try:
        with open(projects_file, "r") as f:
            projects = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    all_notes = []
    for proj in projects:
        uid = proj.get("uid")
        path = proj.get("path")
        if not uid:
            continue

        notes_path = os.path.join(config.config.DATA_DIR_PATH, uid, "notes.json")
        if not os.path.exists(notes_path):
            continue

        try:
            with open(notes_path, "r") as f:
                notes = json.load(f)
                for n in notes:
                    n["project_path"] = path
                all_notes.extend(notes)
        except (json.JSONDecodeError, OSError):
            continue

    return all_notes


def execute(_args: argparse.Namespace) -> None:
    """
    Show the 5 most recent notes from all projects.
    """
    all_notes = _load_all_notes()

    if not all_notes:
        print(colors.dim("No notes found in any project."))
        return

    # Sort by created_at descending
    all_notes.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    # Take top 5
    recent_notes = all_notes[:5]

    term_width = shutil.get_terminal_size().columns

    for _, note in enumerate(recent_notes):
        # We don't have a simple display ID here that makes sense globally,
        # so we'll use the index in this list or just show the hash.
        # Let's show the hash instead of index.
        content = note.get("content", "") or ""
        if content:
            content = content.splitlines()[0]

        timestamp = note.get("created_at", "")
        try:
            dt = datetime.fromisoformat(timestamp)
            timestamp_str = dt.strftime("%d %b, %H:%M")
        except (ValueError, TypeError):
            timestamp_str = timestamp or ""

        uid = note.get("id", "")[:8]
        proj_name = os.path.basename(note.get("project_path", "unknown"))

        # Format: "  [hash]  content (proj)  timestamp"
        prefix = f"{colors.dim(f'[{uid}]')}  "
        suffix = f"  {colors.dim(timestamp_str)}"
        proj_tag = f" {colors.cyan(f'({proj_name})')}"

        # Calculate available space
        fixed_width = (
            len(f"[{uid}]  ") + len(timestamp_str) + len(f" ({proj_name})") + 4
        )
        content_width = max(10, term_width - fixed_width)

        if len(content) > content_width:
            content = content[: content_width - 2] + ".."

        line = f"{prefix}{content.ljust(content_width)}{proj_tag}{suffix}"
        print(line)

        ctx = format_note_context(note)
        if ctx:
            print(ctx)

    print()
