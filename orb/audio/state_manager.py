"""Orb state machine.

States: IDLE, LISTENING, THINKING, SPEAKING.

The manager owns the *target* state and produces a set of continuously blended
parameters (`StateParams`) that the renderer consumes. Transitions are never
abrupt: every parameter eases toward the active preset with a time-constant so
the orb's mood shifts feel organic.

A small amount of automatic behaviour is built in:
* If audio is present above a threshold while in LISTENING/SPEAKING, the audio
  level is fed through to the renderer.
* The host application can drive states explicitly (e.g. an assistant pipeline
  setting THINKING then SPEAKING). A convenience auto-mode infers LISTENING vs
  IDLE from microphone level when no explicit control is given.
"""

from __future__ import annotations

import math
from dataclasses import fields
from enum import Enum

from ..config import STATE_PRESETS, StateParams, Timings


class OrbState(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"


_PARAM_FIELDS = [f.name for f in fields(StateParams)]


class StateManager:
    def __init__(self, timings: Timings | None = None):
        self.timings = timings or Timings()
        self._state = OrbState.IDLE
        self._auto = True
        # Live, smoothly-blended parameter values (start at IDLE preset).
        self._current = {k: getattr(STATE_PRESETS["IDLE"], k) for k in _PARAM_FIELDS}
        # The audio level handed to the renderer (already smoothed upstream).
        self.audio_level = 0.0

    # ------------------------------------------------------------------ #
    # State control
    # ------------------------------------------------------------------ #
    @property
    def state(self) -> OrbState:
        return self._state

    def set_state(self, state: OrbState | str, *, auto: bool = False) -> None:
        if isinstance(state, str):
            state = OrbState(state.upper())
        self._state = state
        if not auto:
            self._auto = False

    def enable_auto(self, enabled: bool = True) -> None:
        self._auto = enabled

    def cycle(self) -> OrbState:
        """Manually advance to the next state (handy for demos / hotkeys)."""
        order = list(OrbState)
        idx = (order.index(self._state) + 1) % len(order)
        self.set_state(order[idx])
        return self._state

    # ------------------------------------------------------------------ #
    # Per-frame update
    # ------------------------------------------------------------------ #
    def update(self, dt: float, audio_level: float) -> None:
        # Auto-mode: infer IDLE <-> LISTENING from incoming audio. Explicit
        # THINKING / SPEAKING states (set by a host) are left untouched.
        if self._auto and self._state in (OrbState.IDLE, OrbState.LISTENING):
            self._state = OrbState.LISTENING if audio_level > 0.04 else OrbState.IDLE

        self.audio_level = audio_level

        target = STATE_PRESETS[self._state.value]
        # Exponential ease toward the target preset (frame-rate independent).
        alpha = 1.0 - math.exp(-dt / max(1e-3, self.timings.state_blend_tau))
        for k in _PARAM_FIELDS:
            cur = self._current[k]
            self._current[k] = cur + (getattr(target, k) - cur) * alpha

    # ------------------------------------------------------------------ #
    # Blended parameter access
    # ------------------------------------------------------------------ #
    def params(self) -> StateParams:
        return StateParams(**self._current)

    def get(self, name: str) -> float:
        return self._current[name]
