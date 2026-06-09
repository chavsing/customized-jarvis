"""
Standalone script to bring the JARVIS window to foreground.
Launched via ShellExecute (not subprocess) so it runs outside our process tree.

Usage: python config\bring_to_front.py
"""

import ctypes
from ctypes import wintypes
import sys
import time
import os

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bring_to_front.log")

def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

WINDOW_TITLE = "J.A.R.V.I.S — MARK XXXIX"
SW_RESTORE = 9
HWND_TOPMOST = wintypes.HWND(-1)
HWND_NOTOPMOST = wintypes.HWND(-2)
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
FLASHW_ALL = 0x03

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def find_jarvis():
    result = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_cb(hwnd, _):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if WINDOW_TITLE in buf.value:
                result.append(hwnd)
        return True
    user32.EnumWindows(enum_cb, 0)
    return result[0] if result else None


def main():
    log("=" * 50)
    log(f"PID: {os.getpid()}")

    hwnd = find_jarvis()
    if not hwnd:
        log(f"❌ Window '{WINDOW_TITLE}' not found!")
        sys.exit(1)

    log(f"Found: HWND={hwnd}, IsIconic={user32.IsIconic(hwnd)}")

    # Topmost → restore → foreground → un-topmost
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.2)

    fg = user32.GetForegroundWindow()
    fg_tid = user32.GetWindowThreadProcessId(fg, None)
    my_tid = kernel32.GetCurrentThreadId()

    if fg_tid and fg_tid != my_tid:
        user32.AttachThreadInput(my_tid, fg_tid, True)

    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    user32.SetActiveWindow(hwnd)

    if fg_tid and fg_tid != my_tid:
        user32.AttachThreadInput(my_tid, fg_tid, False)

    user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

    # Flash
    class FLASHWINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("hwnd", wintypes.HWND),
            ("dwFlags", wintypes.DWORD),
            ("uCount", wintypes.UINT),
            ("dwTimeout", wintypes.DWORD),
        ]
    fi = FLASHWINFO()
    fi.cbSize = ctypes.sizeof(FLASHWINFO)
    fi.hwnd = hwnd
    fi.dwFlags = FLASHW_ALL
    fi.uCount = 5
    fi.dwTimeout = 0
    user32.FlashWindowEx(ctypes.byref(fi))

    is_fg = user32.GetForegroundWindow() == hwnd
    log(f"Done. foreground={is_fg}")
    sys.exit(0 if is_fg else 1)


if __name__ == "__main__":
    main()
