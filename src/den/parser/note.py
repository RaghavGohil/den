import os
import json
import uuid
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from ..config import config
from . import project


class DenBackend:
    def __init__(self):
        self.project = None
        self.project_uid = None
        self.notes_path = None
        self._refresh_project()

    def _refresh_project(self):
        """Refresh project info from the current environment."""
        try:
            self.project = project.get()
            self.project_uid = self.project.get("uid")
            if self.project_uid:
                self.notes_path = Path(
                    os.path.join(config.DATA_DIR_PATH, self.project_uid, "notes.json")
                )
        except (ValueError, OSError):
            self.project = None
            self.project_uid = None
            self.notes_path = None

    def _create_notes_file(self) -> Path:
        """Create the notes file if it doesn't exist."""
        if not self.project_uid:
            self._refresh_project()
            if not self.project_uid:
                raise ValueError("Invalid project entry.")

        note_dir = os.path.join(config.DATA_DIR_PATH, self.project_uid)
        os.makedirs(note_dir, exist_ok=True)
        notes_path = os.path.join(note_dir, "notes.json")

        if not os.path.exists(notes_path):
            with open(notes_path, "w") as f:
                json.dump([], f, indent=4)

        self.notes_path = Path(notes_path)
        return self.notes_path

    def load_notes(self) -> List[Dict[str, Any]]:
        """Load all notes for the current project."""
        if not self.notes_path:
            self._refresh_project()

        if not self.notes_path or not self.notes_path.exists():
            return []

        try:
            with open(self.notes_path, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        except OSError:
            return []

    def save_notes(self, notes: List[Dict[str, Any]]):
        """Save the list of notes to disk."""
        if not self.notes_path or not self.notes_path.exists():
            self._create_notes_file()

        with open(self.notes_path, "w") as f:
            json.dump(notes, f, indent=4)

    def find_note_index(self, note_id: Union[int, str, None]) -> int:
        """
        Find the list index of a note by hash ID (str), or None (recent).
        Returns -1 if not found.
        """
        notes = self.load_notes()
        if not notes:
            return -1

        total = len(notes)

        # Default to the most recent note if no ID is provided
        if note_id is None:
            return total - 1

        # Try as hash ID (prefix of UUID)
        if isinstance(note_id, str):
            for i, n in enumerate(notes):
                if n.get("id", "").startswith(note_id):
                    return i

        return -1

    def add_note(
        self, content: str, reference: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Add a new note."""
        if not self.project_uid:
            self._refresh_project()
            if not self.project_uid:
                raise ValueError("Invalid project entry.")

        notes = self.load_notes()
        note = {
            "created_at": str(datetime.datetime.now()),
            "id": str(uuid.uuid4()),
            "content": content,
        }
        if reference:
            note["reference"] = reference

        notes.append(note)
        self.save_notes(notes)
        return note

    def remove_note(self, note_id: Union[int, str, None]) -> Optional[Dict[str, Any]]:
        """Remove a note by ID."""
        notes = self.load_notes()
        idx = self.find_note_index(note_id)

        if idx == -1:
            return None

        removed = notes.pop(idx)
        self.save_notes(notes)
        return removed

    def edit_note(
        self, note_id: Union[int, str, None], new_content: str
    ) -> Optional[Dict[str, Any]]:
        """Edit a note's content by ID."""
        notes = self.load_notes()
        idx = self.find_note_index(note_id)

        if idx == -1:
            return None

        notes[idx]["content"] = new_content
        self.save_notes(notes)
        return notes[idx]


# Global backend instance
backend = DenBackend()


# For backward compatibility or simpler usage
def add(project_uid: str, args) -> None:
    # This remains for now but uses the backend logic internally if needed
    # though it's better to refactor callers to use backend.add_note()
    content = ""
    reference = None

    if isinstance(args, str):
        content = args.strip()
    else:
        content = " ".join(args.note).strip()
        if hasattr(args, "ref") and args.ref:
            try:
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
        return

    backend.add_note(content, reference)


def remove(project_uid: str, display_id: int) -> Optional[dict]:
    return backend.remove_note(display_id)


def edit(project_uid: str, display_id: int, new_content: str) -> Optional[dict]:
    return backend.edit_note(display_id, new_content)
