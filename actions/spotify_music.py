#spotify_music.py
import time
import subprocess
import platform
import shutil
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

_SYSTEM = platform.system()

def _require_pyautogui():
    if not _PYAUTOGUI:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")

def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    time.sleep(0.3)
    pyautogui.typewrite(text, interval=interval)
    return f"Typed: {text[:60]}{'…' if len(text) > 60 else ''}"

def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    if clear_first:
        _clear_field()
        time.sleep(0.1)

    if len(text) > 20 and _PYPERCLIP:
        pyperclip.copy(text)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        return f"Smart-typed (clipboard): {text[:60]}{'…' if len(text) > 60 else ''}"

    pyautogui.typewrite(text, interval=0.04)
    return f"Smart-typed: {text[:60]}{'…' if len(text) > 60 else ''}"

def _press(key: str) -> str:
    _require_pyautogui()
    pyautogui.press(key)
    return f"Pressed: {key}"

def _hotkey(*keys) -> str:
    _require_pyautogui()
    pyautogui.hotkey(*keys)
    return f"Hotkey: {'+'.join(keys)}"

def _clear_field() -> str:
    _require_pyautogui()
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    return "Field cleared"

def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    _require_pyautogui()
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks)
        return f"{'Double-c' if clicks == 2 else 'C'}licked ({x}, {y}) [{button}]"
    pyautogui.click(button=button, clicks=clicks)
    return f"Clicked at current position [{button}]"

def spotify_music(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Controls Spotify music playback.

    parameters keys:
      action        : (required) one of: search_play, play_pause, next, previous, volume_up, volume_down
      query         : search query for search_play action
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if not action:
        return "No action specified for spotify_music."

    if player:
        player.write_log(f"[Spotify] {action}")

    print(f"[SpotifyMusic] ▶ {action}  {params}")

    try:
        # Ensure Spotify is running
        from actions.open_app import open_app
        open_result = open_app({"app_name": "spotify"}, None, player, session_memory)
        if player:
            player.write_log(f"[Spotify] Launch check: {open_result}")
        time.sleep(2)  # Give Spotify time to load

        if action == "search_play":
            query = params.get("query", "").strip()
            if not query:
                return "No search query provided for Spotify search_play."

            # Focus search bar (Ctrl+L in Spotify)
            _hotkey("ctrl", "l")
            time.sleep(0.5)

            # Clear any existing text and type query
            _clear_field()
            time.sleep(0.2)
            _type(query)
            time.sleep(0.5)

            # Press Enter to search
            _press("enter")
            time.sleep(2)  # Wait for search results

            # Press Enter again to play first result
            _press("enter")

            return f"Searching and playing '{query}' on Spotify."

        elif action == "play_pause":
            # Space bar toggles play/pause in Spotify
            _press("space")
            return "Toggled play/pause on Spotify."

        elif action == "next":
            # Ctrl+Right for next track
            _hotkey("ctrl", "right")
            return "Skipped to next track on Spotify."

        elif action == "previous":
            # Ctrl+Left for previous track
            _hotkey("ctrl", "left")
            return "Went to previous track on Spotify."

        elif action == "volume_up":
            # Ctrl+Up for volume up
            _hotkey("ctrl", "up")
            return "Increased volume on Spotify."

        elif action == "volume_down":
            # Ctrl+Down for volume down
            _hotkey("ctrl", "down")
            return "Decreased volume on Spotify."

        else:
            return f"Unknown Spotify action: '{action}'. Available actions: search_play, play_pause, next, previous, volume_up, volume_down"

    except Exception as e:
        print(f"[SpotifyMusic] ❌ {action}: {e}")
        return f"spotify_music '{action}' failed: {e}"