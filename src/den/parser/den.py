"""
Interactive TUI for den using textual.
Supports Operate, Search, Visual, View, and Add modes.
"""

import os
import sys
import tempfile
import subprocess
import argparse
from enum import Enum, auto

from textual import on
from textual.screen import Screen
from textual.message import Message
from textual.binding import Binding
from textual.reactive import reactive
from textual.app import App, ComposeResult, InvalidThemeError
from textual.widgets import ListView, ListItem, Static, Input, Label
from textual.containers import Horizontal, Vertical, ScrollableContainer

from ..config import config
from .project import get_current_project_uid
from .note import backend
from ..parser.notes_helper import (
    get_reference,
    read_reference_code,
    _format_timestamp,
    format_editor_content,
    parse_editor_content,
)


def _get_note_items(notes_list: "NoteListView") -> list["NoteItem"]:
    """Return a plain list of NoteItem children — safe to index."""
    return [c for c in notes_list.children if isinstance(c, NoteItem)]


class Mode(Enum):
    OPERATE = auto()
    VIEW = auto()
    SEARCH = auto()
    ADD = auto()
    DELETE = auto()


current_mode = Mode.OPERATE
current_project = get_current_project_uid()


class DenApp(App):
    ENABLE_COMMAND_PALETTE = False
    CSS_PATH = "tui.tcss"
    BINDINGS = [("ctrl+q", "pass", "pass")]

    def __init__(self):
        super().__init__()

    def on_mount(self) -> None:
        try:
            self.theme = config.THEME
        except InvalidThemeError:
            print("Please set a valid theme in config.")
        self.push_screen(MainScreen())


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
                yield Vertical(
                    Label("[b]NOTE[/b]\n\n", id="text-accent"),
                    Label(f"{content}", id="text-muted"),
                    id="view-header",
                )
                yield Label()
                if ref:
                    filepath = ref.get("filepath", "")
                    start = ref.get("start_line", "")
                    end = ref.get("end_line", "")
                    code = read_reference_code(ref)
                    context_text = f"[dim]{filepath}:{start}-{end}[/dim]\n\n{code}"
                else:
                    context_text = "No reference attached to this note."
                yield Vertical(
                    Label("[b]REFERENCE[/b]\n\n", id="text-accent"),
                    Label(f"{context_text}", id="text-muted"),
                    id="view-context",
                )

            yield Horizontal(
                Label("[b]q[/b] ", id="text-accent"),
                Label("back", id="text-muted"),
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
    search_active = reactive(False)

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

    def __init__(self):
        super().__init__()
        self.notes: list[dict] = []
        self.search_query = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="main-layout"):
            yield NoteListView(id="notes-list")
            yield BottomPreview(id="bottom-preview")
        yield Input(placeholder="Search...", id="search-input")
        yield Input(placeholder="Add note...", id="add-input")
        yield Horizontal(Label(), id="footer")

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------

    async def _update_footer(self) -> None:
        cues: list[tuple[str, str]] = []  # format cue, desc
        if self.add_mode:
            cues.extend([("esc", "cancel"), ("enter", "add")])
        elif self.select_mode:
            cues.extend([("q", "quit"), ("v", "deselect"), ("d", "delete")])
        elif self.search_active:
            cues.extend(
                [
                    ("q", "back"),
                    ("/", "search"),
                    ("a", "add"),
                    ("e", "edit"),
                    ("d", "delete"),
                    ("v", "select"),
                    ("enter", "view"),
                ]
            )
        else:
            cues.extend(
                [
                    ("q", "quit"),
                    ("/", "search"),
                    ("a", "add"),
                    ("e", "edit"),
                    ("d", "delete"),
                    ("v", "select"),
                    ("enter", "view"),
                ]
            )
        cue_horizontals: list[Horizontal] = []
        for cue, desc in cues:
            cue_horizontals.append(
                Horizontal(
                    Label(f"[b]{cue}[/b] ", id="text-accent"),
                    Label(f"{desc} ", id="text-muted"),
                )
            )

        print(cues)
        footer = self.query_one("#footer", Horizontal)
        await footer.remove_children()
        await footer.mount_all(cue_horizontals)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_mount(self) -> None:
        self.query_one("#search-input").display = False
        self.query_one("#add-input").display = False
        self._reload_notes()
        self.query_one("#notes-list").focus()
        await self._update_footer()

    async def watch_select_mode(self, _: bool) -> None:
        await self._update_footer()

    async def watch_add_mode(self, _: bool) -> None:
        await self._update_footer()

    async def watch_search_active(self, _: bool) -> None:
        await self._update_footer()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _reload_notes(self, index: int | None = None) -> None:
        raw = backend.load_notes()
        self.notes = list(reversed(raw))
        self._update_list(index=index)

    def _update_list(self, index: int | None = None) -> None:
        notes_list = self.query_one("#notes-list", NoteListView)
        notes_list.clear()
        query = self.search_query.lower()
        items_added = 0
        for idx, n in enumerate(self.notes):
            if query in (n.get("content", "") or "").lower():
                notes_list.append(NoteItem(n, idx))
                items_added += 1

        if items_added > 0:
            notes_list.index = min(index if index is not None else 0, items_added - 1)
            self._update_preview()
        else:
            self.query_one("#bottom-preview", BottomPreview).update_preview(None)

    def _current_note(self) -> dict | None:
        """Return the note dict for the currently highlighted item, or None."""
        notes_list = self.query_one("#notes-list", NoteListView)
        items = _get_note_items(notes_list)
        idx = notes_list.index
        if idx is not None and 0 <= idx < len(items):
            item = items[idx]
            if 0 <= item.orig_idx < len(self.notes):
                return self.notes[item.orig_idx]
        return None

    def _update_preview(self) -> None:
        self.query_one("#bottom-preview", BottomPreview).update_preview(
            self._current_note()
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    @on(ListView.Selected)
    def on_list_selected(self, _: ListView.Selected) -> None:
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
        search_input = self.query_one("#search-input", Input)
        search_input.display = True
        search_input.focus()

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        self.search_query = event.value
        self._update_list()
        # If user is typing, we might want to show the search status even before enter
        if self.search_query:
            self.search_active = True
        else:
            self.search_active = False

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self, _: Input.Submitted) -> None:
        if not self.search_query:
            self.query_one("#search-input").display = False
            self.search_active = False
        else:
            self.search_active = True
        self.query_one("#notes-list").focus()

    # ------------------------------------------------------------------
    # Add
    # ------------------------------------------------------------------

    def action_enter_add_mode(self) -> None:
        if self.select_mode or self.add_mode:
            return
        self.add_mode = True
        add_input = self.query_one("#add-input", Input)
        add_input.display = True
        add_input.focus()

    @on(Input.Submitted, "#add-input")
    def on_add_submitted(self, event: Input.Submitted) -> None:
        content = event.value.strip()
        if content:
            backend.add_note(content)
            self._reload_notes(index=0)
        self.add_mode = False
        add_input = self.query_one("#add-input")
        add_input.display = False
        self.query_one("#notes-list").focus()

    # ------------------------------------------------------------------
    # Cancel / Escape
    # ------------------------------------------------------------------

    def action_cancel(self) -> None:
        search_input = self.query_one("#search-input")
        add_input = self.query_one("#add-input")

        if search_input.display:
            search_input.display = False
            self.search_query = ""
            self.search_active = False
            self._update_list()
            self.query_one("#notes-list").focus()
        elif add_input.display:
            add_input.display = False
            self.add_mode = False
            self.query_one("#notes-list").focus()
        elif self.search_active:
            self.search_query = ""
            self.search_active = False
            self._reload_notes()
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

    async def action_delete_notes(self) -> None:
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
            note_data = self.notes[item.orig_idx]
            backend.remove_note(note_data.get("id"))

        if self.select_mode:
            notes_list.select_mode = False
            notes_list._clear_selection()
            notes_list.selection_start_index = None
            self.select_mode = False
            await self._update_footer()

        self._reload_notes(index=old_index)

    # ------------------------------------------------------------------
    # Edit
    # ------------------------------------------------------------------

    def action_edit_note(self) -> None:
        if self.select_mode or self.add_mode or not self.notes:
            return
        n = self._current_note()
        if not n:
            raise TypeError("Current note is None!")

        # We need the display_id (orig_idx + 1) for the editor
        # Find the item again to be sure
        notes_list = self.query_one("#notes-list", NoteListView)
        items = _get_note_items(notes_list)
        idx = notes_list.index
        if idx is None or not (0 <= idx < len(items)):
            return

        editor = os.environ.get("EDITOR", "nano")
        self._suspend_and_run_editor(
            editor, format_editor_content(n), n, n.get("id"), idx
        )

    def _suspend_and_run_editor(
        self, editor: str, editor_text: str, n: dict, note_id: str, current_idx: int
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
                    backend.edit_note(note_id, new_content)
            except Exception:
                pass
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
        self._reload_notes(index=current_idx)

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
        if self.search_active:
            self.search_query = ""
            self.search_active = False
            search_input = self.query_one("#search-input")
            search_input.display = False
            self._reload_notes()
            return
        sys.exit(0)


def execute(_: argparse.Namespace) -> None:
    DenApp().run()
