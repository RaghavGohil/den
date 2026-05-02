import pytest
from unittest.mock import MagicMock, patch
from textual.widgets import ListView, Input, Footer
from den.parser.den import DenApp, NoteItem, MainScreen

@pytest.fixture
def mock_notes():
    return [
        {"content": "Note 1", "created_at": "2023-01-01T10:00:00", "id": "1"},
        {"content": "Note 2", "created_at": "2023-01-01T11:00:00", "id": "2"},
        {"content": "Note 3", "created_at": "2023-01-01T12:00:00", "id": "3"},
    ]

@pytest.mark.asyncio
async def test_app_mount(mock_notes):
    with patch("den.parser.den.load_notes", return_value=mock_notes), \
         patch("den.parser.den.get_reference", return_value=None):
        app = DenApp("test_project")
        async with app.run_test() as pilot:
            screen = app.screen
            notes_list = screen.query_one("#notes-list", ListView)
            assert len(notes_list.children) == 3
            # Newest first, so Note 3 should be first
            item = notes_list.children[0]
            assert "Note 3" in str(item.query_one(".note-content").render())

@pytest.mark.asyncio
async def test_search(mock_notes):
    with patch("den.parser.den.load_notes", return_value=mock_notes), \
         patch("den.parser.den.get_reference", return_value=None):
        app = DenApp("test_project")
        async with app.run_test() as pilot:
            # Press '/' to search
            await pilot.press("/")
            screen = app.screen
            search_input = screen.query_one("#search-input", Input)
            assert search_input.display is True
            
            # Type "Note 1"
            for char in "Note 1":
                if char == " ":
                    await pilot.press("space")
                else:
                    await pilot.press(char)
            await pilot.press("enter")
            
            notes_list = screen.query_one("#notes-list", ListView)
            assert len(notes_list.children) == 1
            item = notes_list.children[0]
            assert "Note 1" in str(item.query_one(".note-content").render())

@pytest.mark.asyncio
async def test_vim_select_mode_and_delete(mock_notes):
    with patch("den.parser.den.load_notes", return_value=mock_notes), \
         patch("den.parser.den.get_reference", return_value=None), \
         patch("den.parser.note.remove", return_value={"content": "removed"}) as mock_remove:
        
        app = DenApp("test_project")
        async with app.run_test() as pilot:
            # Wait for MainScreen to be pushed
            await pilot.pause()
            screen = app.screen
            # Toggle select mode
            await pilot.press("v")
            await pilot.pause()
            assert getattr(screen, "select_mode", False) is True
            
            # Move down to select the second note (Note 2)
            notes_list = screen.query_one("#notes-list")
            await pilot.press("j")
            await pilot.pause()
            
            # Both Note 3 and Note 2 should be selected now
            selected_items = [item for item in notes_list.query(NoteItem) if item.is_selected]
            assert len(selected_items) == 2
            
            # Delete selected
            await pilot.press("d")
            
            # note.remove should have been called twice
            assert mock_remove.call_count == 2
            assert screen.select_mode is False

@pytest.mark.asyncio
async def test_add_mode(mock_notes):
    with patch("den.parser.den.load_notes", return_value=mock_notes), \
         patch("den.parser.den.get_reference", return_value=None), \
         patch("den.parser.note.add", return_value={"content": "new note"}) as mock_add:
        
        app = DenApp("test_project")
        async with app.run_test() as pilot:
            # Press 'A' to add (Shift+a)
            await pilot.press("A")
            screen = app.screen
            add_input = screen.query_one("#add-input", Input)
            assert add_input.display is True
            assert getattr(screen, "add_mode", False) is True
            
            # Type "New Note"
            for char in "New Note":
                if char == " ":
                    await pilot.press("space")
                else:
                    await pilot.press(char)
            await pilot.press("enter")
            
            # note.add should have been called
            mock_add.assert_called_once()
            assert screen.add_mode is False
            assert add_input.display is False

@pytest.mark.asyncio
async def test_view_mode(mock_notes):
    with patch("den.parser.den.load_notes", return_value=mock_notes), \
         patch("den.parser.den.get_reference", return_value=None):
        
        app = DenApp("test_project")
        async with app.run_test() as pilot:
            # Press 'enter' to view
            await pilot.press("enter")
            
            # Check if FullScreenView is pushed
            from den.parser.den import FullScreenView
            assert isinstance(app.screen, FullScreenView)
            
            # Press 'q' to go back
            await pilot.press("q")
            assert isinstance(app.screen, MainScreen)
