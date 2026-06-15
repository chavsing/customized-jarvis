"""OrbHud — drop-in replacement for the old QPainter HudCanvas, backed by the
GPU orb engine (orb/ package: moderngl + GLSL shaders).

JARVIS drives it through three methods:
    set_orb_state("LISTENING"|"THINKING"|"PROCESSING"|"SPEAKING"|...)
    set_muted(bool)
    set_level(float)   # output-audio amplitude 0..1 -> orb reactivity

It maps JARVIS's states onto the orb's IDLE/LISTENING/THINKING/SPEAKING and is
fed amplitude via ExternalAnalyzer (no second microphone stream).
"""

from __future__ import annotations

from orb.window import OrbGLWidget
from orb.audio import ExternalAnalyzer, OrbState, StateManager

_STATE_MAP = {
    "SPEAKING": OrbState.SPEAKING,
    "THINKING": OrbState.THINKING,
    "PROCESSING": OrbState.THINKING,
    "LISTENING": OrbState.LISTENING,
    "INITIALISING": OrbState.IDLE,
    "IDLE": OrbState.IDLE,
}


class OrbHud(OrbGLWidget):
    def __init__(self, face_path: str | None = None, parent=None):
        self._ext = ExternalAnalyzer()
        sm = StateManager()
        sm.enable_auto(False)          # JARVIS sets state explicitly
        super().__init__(self._ext, sm, parent)
        self._state_name = "INITIALISING"
        self._muted = False

    # ---- JARVIS-facing control API ----
    def set_orb_state(self, state: str) -> None:
        self._state_name = (state or "").upper()
        self._refresh()

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self._refresh()

    def set_level(self, level: float) -> None:
        self._ext.set_level(level)

    def _refresh(self) -> None:
        target = OrbState.IDLE if self._muted else _STATE_MAP.get(self._state_name, OrbState.IDLE)
        self.state.set_state(target)

    # ---- Disable the standalone window drag/resize when embedded ----
    def mousePressEvent(self, e):   # noqa: D401
        pass

    def mouseMoveEvent(self, e):
        pass

    def mouseReleaseEvent(self, e):
        pass

    def wheelEvent(self, e):
        pass
