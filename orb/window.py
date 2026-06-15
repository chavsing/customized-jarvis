"""PyQt6 transparent, frameless, always-on-top window hosting the orb.

The orb is drawn by `OrbGLWidget`, a `QOpenGLWidget` that creates a ModernGL
context over Qt's GL surface. A QTimer paces repaints at the target FPS; actual
frame timing is measured so all animation is frame-rate independent.

Interaction
-----------
* Drag anywhere      : move the window
* Mouse wheel        : resize the orb
* Space              : cycle state (IDLE -> LISTENING -> THINKING -> SPEAKING)
* 1 / 2 / 3 / 4      : set state directly
* A                  : toggle automatic (mic-driven) state
* T                  : always-on-top toggle
* Esc / Q            : quit
"""

from __future__ import annotations

import moderngl
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

from .audio import AudioAnalyzer, OrbState, StateManager
from .config import CONFIG
from .renderer import OrbRenderer


def make_surface_format() -> QSurfaceFormat:
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setAlphaBufferSize(8)            # required for a transparent surface
    fmt.setDepthBufferSize(0)
    fmt.setStencilBufferSize(0)
    fmt.setSamples(0)                    # we do our own AA via bloom/soft edges
    fmt.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    return fmt


class OrbGLWidget(QOpenGLWidget):
    def __init__(self, analyzer: AudioAnalyzer, state: StateManager, parent=None):
        super().__init__(parent)
        self.analyzer = analyzer
        self.state = state
        self.ctx: moderngl.Context | None = None
        self.renderer: OrbRenderer | None = None

        self._elapsed = QtCore.QElapsedTimer()
        self._last_ns = 0
        self._time = 0.0
        self._drag_pos: QtCore.QPoint | None = None

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.update)

        self.setMouseTracking(False)

    # ----------------------------- GL ----------------------------------- #
    def initializeGL(self) -> None:
        self.ctx = moderngl.create_context()
        self.renderer = OrbRenderer(self.ctx)
        dpr = self.devicePixelRatioF()
        self.renderer.resize(int(self.width() * dpr), int(self.height() * dpr))
        self._elapsed.start()
        self._last_ns = self._elapsed.nsecsElapsed()
        self._timer.start(max(1, int(1000 / CONFIG.window.target_fps)))

    def resizeGL(self, w: int, h: int) -> None:
        if self.renderer is not None:
            dpr = self.devicePixelRatioF()
            self.renderer.resize(int(w * dpr), int(h * dpr))

    def paintGL(self) -> None:
        if self.renderer is None or self.ctx is None:
            return

        now = self._elapsed.nsecsElapsed()
        dt = (now - self._last_ns) / 1e9
        self._last_ns = now
        dt = min(dt, 0.05)               # clamp huge stalls (e.g. after a drag)
        self._time += dt

        audio = self.analyzer.poll()
        self.state.update(dt, audio)
        params = self.state.params()

        screen = self.ctx.detect_framebuffer()
        self.renderer.render(
            self._time, dt, audio, params, screen, dpr=self.devicePixelRatioF()
        )

    def cleanup(self) -> None:
        self.makeCurrent()
        if self.renderer is not None:
            self.renderer.release()
        self.doneCurrent()

    # --------------------------- Interaction ---------------------------- #
    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent) -> None:
        self._drag_pos = None
        super().mouseReleaseEvent(e)

    def mouseMoveEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.buttons() & Qt.MouseButton.LeftButton and self._drag_pos is not None:
            win = self.window()
            point = e.globalPosition().toPoint()
            delta = point - self._drag_pos
            win.move(win.pos() + delta)
            self._drag_pos = point
        super().mouseMoveEvent(e)

    def wheelEvent(self, e: QtGui.QWheelEvent) -> None:
        win = self.window()
        step = 40 if e.angleDelta().y() > 0 else -40
        size = win.size()
        win.resize(max(160, size.width() + step), max(160, size.height() + step))


class OrbWindow(QtWidgets.QWidget):
    """Top-level frameless / translucent / always-on-top container."""

    def __init__(self, analyzer: AudioAnalyzer, state: StateManager):
        super().__init__()
        self.state = state
        self._always_on_top = CONFIG.window.always_on_top

        flags = Qt.WindowType.Window
        if CONFIG.window.frameless:
            flags |= Qt.WindowType.FramelessWindowHint
        if self._always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        if CONFIG.window.transparent:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(CONFIG.window.title)
        self.resize(CONFIG.window.width, CONFIG.window.height)

        self.gl = OrbGLWidget(analyzer, state, self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.gl)

    # --------------------------- Hotkeys -------------------------------- #
    def keyPressEvent(self, e: QtGui.QKeyEvent) -> None:
        key = e.key()
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Q):
            self.close()
        elif key == Qt.Key.Key_Space:
            self.state.cycle()
        elif key == Qt.Key.Key_1:
            self.state.set_state(OrbState.IDLE)
        elif key == Qt.Key.Key_2:
            self.state.set_state(OrbState.LISTENING)
        elif key == Qt.Key.Key_3:
            self.state.set_state(OrbState.THINKING)
        elif key == Qt.Key.Key_4:
            self.state.set_state(OrbState.SPEAKING)
        elif key == Qt.Key.Key_A:
            self.state.enable_auto(True)
        elif key == Qt.Key.Key_T:
            self._toggle_on_top()
        else:
            super().keyPressEvent(e)

    def _toggle_on_top(self) -> None:
        self._always_on_top = not self._always_on_top
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._always_on_top)
        self.show()  # re-applying flags requires re-showing the window

    def closeEvent(self, e: QtGui.QCloseEvent) -> None:
        self.gl.cleanup()
        super().closeEvent(e)
