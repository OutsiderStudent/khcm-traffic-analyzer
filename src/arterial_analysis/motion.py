from __future__ import annotations

import os

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QGraphicsOpacityEffect,
    QTabWidget,
    QWidget,
)


class MotionController(QObject):
    """Short tactile motion that does not delay spreadsheet-style input."""

    PRESS_OPACITY = 0.68
    PRESS_MS = 70
    RELEASE_MS = 170
    PAGE_MS = 190
    DIALOG_MS = 180

    def __init__(self, app: QApplication, reduced_motion: bool | None = None):
        super().__init__(app)
        self.app = app
        if reduced_motion is None:
            reduced_motion = os.environ.get("KHCM_REDUCE_MOTION", "").strip().lower() in {"1", "true", "yes", "on"}
        self.reduced_motion = reduced_motion
        self._animations: dict[tuple[int, bytes], QPropertyAnimation] = {}

    def bind(self, root: QWidget) -> None:
        self.app.installEventFilter(self)
        for tabs in root.findChildren(QTabWidget):
            if tabs.property("khcmMotionBound"):
                continue
            tabs.setProperty("khcmMotionBound", True)
            tabs.currentChanged.connect(lambda index, target=tabs: self.fade_widget(target.widget(index)))

    def _run(self, target: QObject, property_name: bytes, start: float, end: float, duration: int, easing) -> None:
        key = (id(target), property_name)
        previous = self._animations.pop(key, None)
        if previous is not None:
            previous.stop()
        animation = QPropertyAnimation(target, property_name, self)
        animation.setDuration(0 if self.reduced_motion else duration)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(easing)
        self._animations[key] = animation

        def finished() -> None:
            if self._animations.get(key) is animation:
                self._animations.pop(key, None)
            animation.deleteLater()

        animation.finished.connect(finished)
        animation.start()

    @staticmethod
    def _button_effect(button: QAbstractButton) -> QGraphicsOpacityEffect:
        effect = button.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(button)
            effect.setOpacity(1.0)
            button.setGraphicsEffect(effect)
        return effect

    def press_button(self, button: QAbstractButton) -> None:
        if not button.isEnabled():
            return
        effect = self._button_effect(button)
        self._run(effect, b"opacity", effect.opacity(), self.PRESS_OPACITY, self.PRESS_MS, QEasingCurve.OutQuad)

    def release_button(self, button: QAbstractButton) -> None:
        effect = self._button_effect(button)
        self._run(effect, b"opacity", effect.opacity(), 1.0, self.RELEASE_MS, QEasingCurve.OutCubic)

    def fade_widget(self, widget: QWidget | None) -> None:
        if widget is None or self.reduced_motion:
            return
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.25)
        widget.setGraphicsEffect(effect)
        self._run(effect, b"opacity", 0.25, 1.0, self.PAGE_MS, QEasingCurve.OutCubic)

        def clear_effect() -> None:
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)

        animation = self._animations.get((id(effect), b"opacity"))
        if animation is not None:
            animation.finished.connect(clear_effect)

    def _fade_dialog(self, dialog: QDialog) -> None:
        if self.reduced_motion or QApplication.platformName().lower() == "offscreen":
            return
        dialog.setWindowOpacity(0.0)
        self._run(dialog, b"windowOpacity", 0.0, 1.0, self.DIALOG_MS, QEasingCurve.OutCubic)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QAbstractButton):
            if event.type() == QEvent.MouseButtonPress:
                self.press_button(watched)
            elif event.type() in (QEvent.MouseButtonRelease, QEvent.Leave):
                self.release_button(watched)
            elif event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
                self.press_button(watched)
            elif event.type() == QEvent.KeyRelease and event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
                self.release_button(watched)
        elif isinstance(watched, QDialog) and event.type() == QEvent.Show:
            self._fade_dialog(watched)
        return super().eventFilter(watched, event)
