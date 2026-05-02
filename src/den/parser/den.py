"""
Interactive TUI for den using textual.
Supports Operate, Search, Visual, View, and Add modes.
"""

import argparse
import os
import sys
import tempfile
import subprocess

from textual.app import App, ComposeResult, InvalidThemeError
from textual.widgets import ListView, ListItem, Static, Input, Label
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.binding import Binding
from textual.screen import Screen
from textual import on
from textual.message import Message
from textual.reactive import reactive

from ..config import THEME
from . import note, project
from ..parser.notes_helper import (
    load_notes,
    get_reference,
    read_reference_code,
    _format_timestamp,
    format_editor_content,
    parse_editor_content,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_note_items(notes_list: "NoteListView") -> list["NoteItem"]:
    """Return a plain list of NoteItem children — safe to index."""
    return [c for c in notes_list.children if isinstance(c, NoteItem)]


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------


class NoteItem(ListItem):
    """A single row in the note list."""

    is_selected = reactive(False)

    def __init__(self, note_data: dict, orig_idx: int):
        super().__init__()
        self.note_data = note_data
        self.orig_idx = orig_idx

    def compose(self) -> ComposeResult:
        content = self.note_data.get("content", "") or ""
        uid = self.note_data.get("id", "")
        timestamp = _format_timestamp(self.note_data.get("created_at", ""))
        ref = get_reference(self.note_data)
        display_id = self.orig_idx + 1

        with Horizontal(classes="note-item-layout"):
            yield Label(f"{uid[:8]}", classes="note-uid")
            yield Label(f"{display_id}", classes="note-id")
            with Vertical(classes="note-content-container"):
                yield Label(content, classes="note-content")
                if ref:
                    basename = os.path.basename(ref.get("filepath", ""))
                    yield Label(basename, classes="note-ref")
            yield Label(timestamp, classes="note-time")

    def watch_is_selected(self, value: bool) -> None:
        self.set_class(value, "selected")


class NoteListView(ListView):
    """ListView with Vim-style navigation and visual selection."""

    BINDINGS = [
        Binding("j", "cursor_down", "down", show=False),
        Binding("k", "cursor_up", "up", show=False),
        Binding("down", "cursor_down", "down", show=False),
        Binding("up", "cursor_up", "up", show=False),
        Binding("v", "toggle_mode", "select", show=False),
    ]

    class ModeChanged(Message):
        def __init__(self, select_mode: bool):
            super().__init__()
            self.select_mode = select_mode

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.select_mode = False
        self.selection_start_index: int | None = None

    def action_toggle_mode(self) -> None:
        self.select_mode = not self.select_mode
        if self.select_mode:
            self.selection_start_index = self.index
            self._update_selection()
        else:
            self._clear_selection()
            self.selection_start_index = None
        self.post_message(self.ModeChanged(self.select_mode))

    def _clear_selection(self) -> None:
        for item in self.query(NoteItem):
            item.is_selected = False

    def _update_selection(self) -> None:
        if self.selection_start_index is None or self.index is None:
            return
        start = min(self.selection_start_index, self.index)
        end = max(self.selection_start_index, self.index)
        for i, item in enumerate(_get_note_items(self)):
            item.is_selected = start <= i <= end

    def action_cursor_down(self) -> None:
        super().action_cursor_down()
        if self.select_mode:
            self._update_selection()

    def action_cursor_up(self) -> None:
        super().action_cursor_up()
        if self.select_mode:
            self._update_selection()


class BottomPreview(Static):
    """
    Compact single-line strip docked below the list.
    Shows the first line of content + ref filename if present.
    Full content is only accessible via FullScreenView (Enter).
    """

    def update_preview(self, note_data: dict | None) -> None:
        if not note_data:
            self.display = False
            return

        ref = get_reference(note_data)
        if not ref:
            self.display = False
            return

        filepath = ref.get("filepath", "")
        start = ref.get("start_line", "")
        end = ref.get("end_line", "")
        self.display = True
        self.update(f"[dim]ref:[/dim] {filepath}:{start}-{end}")


# ---------------------------------------------------------------------------
# Full-screen view (Enter)
# ---------------------------------------------------------------------------


class FullScreenView(Screen):
    """Full-screen read-only view for a single note."""

    BINDINGS = [
        Binding("q", "app.pop_screen", "back"),
        Binding("j", "scroll_down", "scroll down", show=False),
        Binding("k", "scroll_up", "scroll up", show=False),
        Binding("down", "scroll_down", "scroll down", show=False),
        Binding("up", "scroll_up", "scroll up", show=False),
    ]

    def __init__(self, note_data: dict):
        super().__init__()
        self.note_data = note_data

    def compose(self) -> ComposeResult:
        content = self.note_data.get("content", "") or "[dim]No note content.[/dim]"
        ref = get_reference(self.note_data)

        with Vertical(id="view-container"):
            with ScrollableContainer(id="view-scroll-area"):
                yield Label(
                    f"[overline][b] NOTE [/b][/overline]\n\n{content}",
                    id="view-header",
                )
                if ref:
                    filepath = ref.get("filepath", "")
                    start = ref.get("start_line", "")
                    end = ref.get("end_line", "")
                    code = read_reference_code(ref)
                    context_text = (
                        f"[overline][b] REFERENCE [/b][/overline] "
                        f"[dim]{filepath}:{start}-{end}[/dim]\n\n{code}"
                    )
                else:
                    context_text = "\n[dim]No reference attached to this note.[/dim]"
                yield Label(context_text, id="view-context")
            yield Static(
                "[b][#fad166]q[/#fad166][/b] back",
                id="footer",
            )

    def action_scroll_down(self) -> None:
        self.query_one("#view-scroll-area").scroll_relative(y=3)

    def action_scroll_up(self) -> None:
        self.query_one("#view-scroll-area").scroll_relative(y=-3)


# ---------------------------------------------------------------------------
# Main screen
# ---------------------------------------------------------------------------


class MainScreen(Screen):
    """Main screen: list + bottom preview strip."""

    select_mode = reactive(False)
    add_mode = reactive(False)

    BINDINGS = [
        Binding("q", "quit_system", "quit"),
        Binding("/", "search", "search"),
        Binding("j", "cursor_down", "down", show=False),
        Binding("k", "cursor_up", "up", show=False),
        Binding("e", "edit_note", "edit"),
        Binding("d", "delete_notes", "delete"),
        Binding("v", "toggle_mode", "select"),
        Binding("a", "enter_add_mode", "add"),
        Binding("enter", "view_note", "view"),
        Binding("escape", "cancel", "cancel", show=False),
    ]

    def __init__(self, project_uid: str):
        super().__init__()
        self.project_uid = project_uid
        self.notes: list[dict] = []
        self.search_query = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="main-layout"):
            yield NoteListView(id="notes-list")
            yield BottomPreview(id="bottom-preview")
        yield Input(placeholder="Search...", id="search-input")
        yield Input(placeholder="Add note...", id="add-input")
        yield Static("", id="footer")

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    def _update_footer(self) -> None:
        if self.add_mode:
            text = "[b][#fad166]esc[/#fad166][/b] cancel  [b][#fad166]enter[/#fad166][/b] add"
        elif self.select_mode:
            text = "[b][#fad166]esc[/#fad166][/b] deselect  [b][#fad166]d[/#fad166][/b] delete"
        else:
            text = (
                "[b][#fad166]q[/#fad166][/b] quit  "
                "[b][#fad166]/[/#fad166][/b] search  "
                "[b][#fad166]a[/#fad166][/b] add  "
                "[b][#fad166]e[/#fad166][/b] edit  "
                "[b][#fad166]d[/#fad166][/b] delete  "
                "[b][#fad166]v[/#fad166][/b] select  "
                "[b][#fad166]enter[/#fad166][/b] view"
            )
        try:
            self.query_one("#footer", Static).update(text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self.query_one("#search-input").display = False
        self.query_one("#add-input").display = False
        self._reload_notes()
        self.query_one("#notes-list").focus()
        self._update_footer()

    def watch_select_mode(self, value: bool) -> None:
        self._update_footer()

    def watch_add_mode(self, value: bool) -> None:
        self._update_footer()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _reload_notes(self) -> None:
        raw = load_notes(self.project_uid)
        self.notes = list(reversed(raw))
        self._update_list()

    def _update_list(self) -> None:
        notes_list = self.query_one("#notes-list", NoteListView)
        notes_list.clear()
        query = self.search_query.lower()
        for idx, n in enumerate(self.notes):
            if query in (n.get("content", "") or "").lower():
                notes_list.append(NoteItem(n, idx))

        if _get_note_items(notes_list):
            notes_list.index = 0
            self._update_preview()
        else:
            self.query_one("#bottom-preview", BottomPreview).update_preview(None)

    def _current_note(self) -> dict | None:
        """Return the note dict for the currently highlighted item, or None."""
        notes_list = self.query_one("#notes-list", NoteListView)
        items = _get_note_items(notes_list)
        idx = notes_list.index
        if idx is not None and 0 <= idx < len(items):
            return self.notes[items[idx].orig_idx]
        return None

    def _update_preview(self) -> None:
        self.query_one("#bottom-preview", BottomPreview).update_preview(
            self._current_note()
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        if self.select_mode or self.add_mode:
            return
        n = self._current_note()
        if n:
            self.app.push_screen(FullScreenView(n))

    @on(ListView.Highlighted)
    def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        for item in self.query(NoteItem):
            item.remove_class("--highlighted")
        if event.item:
            event.item.add_class("--highlighted")
        self._update_preview()

    @on(NoteListView.ModeChanged)
    def on_mode_changed(self, event: NoteListView.ModeChanged) -> None:
        self.select_mode = event.select_mode

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def action_search(self) -> None:
        if self.select_mode or self.add_mode:
            return
        search_input = self.query_one("#search-input")
        search_input.display = True
        search_input.focus()

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        self.search_query = event.value
        self._update_list()

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        self.query_one("#search-input").display = False
        self.query_one("#notes-list").focus()

    # ------------------------------------------------------------------
    # Add
    # ------------------------------------------------------------------

    def action_enter_add_mode(self) -> None:
        if self.select_mode or self.add_mode:
            return
        self.add_mode = True
        add_input = self.query_one("#add-input")
        add_input.display = True
        add_input.focus()

    @on(Input.Submitted, "#add-input")
    def on_add_submitted(self, event: Input.Submitted) -> None:
        content = event.value.strip()
        if content:
            note.add(self.project_uid, content)
            self._reload_notes()
        self.add_mode = False
        add_input = self.query_one("#add-input")
        add_input.value = ""
        add_input.display = False
        self.query_one("#notes-list").focus()

    # ------------------------------------------------------------------
    # Cancel / Escape
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        search_input = self.query_one("#search-input")
        add_input = self.query_one("#add-input")

        if search_input.display:
            search_input.value = ""
            search_input.display = False
            self.search_query = ""
            self._update_list()
            self.query_one("#notes-list").focus()
        elif add_input.display:
            add_input.value = ""
            add_input.display = False
            self.add_mode = False
            self.query_one("#notes-list").focus()
        elif self.select_mode:
            self.query_one("#notes-list", NoteListView).action_toggle_mode()

    # ------------------------------------------------------------------
    # Visual select
    # ------------------------------------------------------------------

    def action_toggle_mode(self) -> None:
        if self.add_mode:
            return
        self.query_one("#notes-list", NoteListView).action_toggle_mode()

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def action_delete_notes(self) -> None:
        if self.add_mode:
            return

        notes_list = self.query_one("#notes-list", NoteListView)
        items = _get_note_items(notes_list)

        if self.select_mode:
            to_delete = [item for item in items if item.is_selected]
            if not to_delete:
                return
        else:
            idx = notes_list.index
            if idx is None or not items:
                return
            to_delete = [items[idx]]

        old_index = notes_list.index or 0

        for item in sorted(to_delete, key=lambda x: x.orig_idx, reverse=True):
            note.remove(self.project_uid, item.orig_idx + 1)

        if self.select_mode:
            notes_list.select_mode = False
            notes_list._clear_selection()
            notes_list.selection_start_index = None
            self.select_mode = False
            self._update_footer()

        raw = load_notes(self.project_uid)
        self.notes = list(reversed(raw))
        self._update_list()

        new_items = _get_note_items(notes_list)
        if new_items:
            notes_list.index = min(old_index, len(new_items) - 1)
            self._update_preview()

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------

    def action_edit_note(self) -> None:
        if self.select_mode or self.add_mode or not self.notes:
            return
        notes_list = self.query_one("#notes-list", NoteListView)
        items = _get_note_items(notes_list)
        idx = notes_list.index
        if idx is None or not items:
            return
        item = items[idx]
        n = self.notes[item.orig_idx]
        editor = os.environ.get("EDITOR", "nano")
        self._suspend_and_run_editor(
            editor, format_editor_content(n), n, item.orig_idx + 1
        )

    def _suspend_and_run_editor(
        self, editor: str, editor_text: str, n: dict, display_id: int
    ) -> None:
        tmp_path: str | None = None
        with self.app.suspend():
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", prefix="den_edit_", delete=False
                ) as tmp:
                    tmp.write(editor_text)
                    tmp_path = tmp.name
                subprocess.run([editor, tmp_path], check=True)
                with open(tmp_path, "r") as f:
                    new_content = parse_editor_content(f.read())
                if new_content != n.get("content", ""):
                    note.edit(self.project_uid, display_id, new_content)
            except Exception:
                pass
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
        self._reload_notes()

    # ------------------------------------------------------------------
    # View (Enter → full screen)
    # ------------------------------------------------------------------

    def action_view_note(self) -> None:
        if self.select_mode or self.add_mode:
            return
        n = self._current_note()
        if n:
            self.app.push_screen(FullScreenView(n))

    # ------------------------------------------------------------------
    # Navigation delegation
    # ------------------------------------------------------------------

    def action_cursor_down(self) -> None:
        self.query_one("#notes-list", NoteListView).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#notes-list", NoteListView).action_cursor_up()

    def action_quit_system(self) -> None:
        sys.exit(0)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class DenApp(App):
    ENABLE_COMMAND_PALETTE = False
    CSS_PATH = "tui.tcss"
    BINDINGS = [("ctrl+q", "pass", "pass")]

    def __init__(self, project_uid: str):
        super().__init__()
        self.project_uid = project_uid

    def on_mount(self) -> None:
        try:
            self.theme = THEME
        except InvalidThemeError:
            print("Please set a valid theme in config.")
        self.push_screen(MainScreen(self.project_uid))


def _get_project_uid() -> str:
    try:
        proj = project.get()
        return proj.get("uid")
    except Exception:
        sys.exit(1)


def execute(args: argparse.Namespace) -> None:
    DenApp(_get_project_uid()).run()
