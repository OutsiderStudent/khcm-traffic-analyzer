from __future__ import annotations

import os

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QRectF, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QGraphicsOpacityEffect,
    QProxyStyle,
    QStyle,
    QStyleOptionButton,
    QTabWidget,
    QWidget,
)


class TactileProxyStyle(QProxyStyle):
    """배경은 탄성 있게 눌리고 글자는 원해상도로 유지되는 버튼 스타일."""

    def drawControl(self, element, option, painter, widget=None):
        if element == QStyle.ControlElement.CE_PushButton and isinstance(widget, QAbstractButton):
            progress = max(-0.14, min(1.0, float(widget.property("khcmPressProgress") or 0.0)))
            hover = max(0.0, min(1.0, float(widget.property("khcmHoverProgress") or 0.0)))
            if abs(progress) < 0.001 and hover < 0.001:
                super().drawControl(element, option, painter, widget)
                return
            scale = 1.0 - 0.072 * progress
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.translate(widget.width() / 2, widget.height() / 2)
            painter.scale(scale, scale)
            painter.translate(-widget.width() / 2, -widget.height() / 2)
            super().drawControl(QStyle.ControlElement.CE_PushButtonBevel, option, painter, widget)
            painter.restore()

            # A short blue halo makes hover/press feedback visible without rasterizing text.
            painter.save()
            rect = QRectF(widget.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            halo = QColor(35, 117, 232, int(78 * hover + 42 * max(0.0, progress)))
            painter.setPen(QPen(halo, 1.4 + 0.8 * max(0.0, progress)))
            painter.setBrush(QColor(35, 117, 232, int(13 * max(0.0, progress))))
            painter.drawRoundedRect(rect, 8.0, 8.0)
            painter.restore()

            # Never transform or vertically offset glyphs; this fixes compact-button blur.
            label_option = QStyleOptionButton(option)
            label_option.state &= ~QStyle.StateFlag.State_Sunken
            super().drawControl(QStyle.ControlElement.CE_PushButtonLabel, label_option, painter, widget)
            return
        super().drawControl(element, option, painter, widget)


class MotionController(QObject):
    """Short tactile motion that does not delay spreadsheet-style input."""

    PRESS_MS = 95
    RELEASE_MS = 260
    HOVER_IN_MS = 140
    HOVER_OUT_MS = 190
    PAGE_MS = 190
    DIALOG_MS = 180

    def __init__(self, app: QApplication, reduced_motion: bool | None = None):
        super().__init__(app)
        self.app = app
        if reduced_motion is None:
            values = (os.environ.get("KHCM_REDUCE_MOTION", ""), os.environ.get("KGSS_REDUCE_MOTION", ""))
            reduced_motion = QApplication.platformName().lower() == "offscreen" or any(value.strip().lower() in {"1", "true", "yes", "on"} for value in values)
        self.reduced_motion = reduced_motion
        self._animations: dict[tuple[int, bytes], QPropertyAnimation] = {}
        self._button_animations: dict[tuple[int, str], QVariantAnimation] = {}

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

    def _animate_button(self, button: QAbstractButton, property_name: str, end: float, duration: int, easing) -> None:
        key = (id(button), property_name)
        previous = self._button_animations.pop(key, None)
        if previous is not None:
            previous.stop()
        start = float(button.property(property_name) or 0.0)
        if self.reduced_motion or not button.isEnabled():
            button.setProperty(property_name, 0.0)
            button.update()
            return
        animation = QVariantAnimation(self)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setDuration(duration)
        animation.setEasingCurve(easing)

        def changed(value) -> None:
            lower = -0.14 if property_name == "khcmPressProgress" else 0.0
            button.setProperty(property_name, max(lower, min(1.0, float(value))))
            button.update()

        def finished() -> None:
            if self._button_animations.get(key) is animation:
                self._button_animations.pop(key, None)
            animation.deleteLater()

        animation.valueChanged.connect(changed)
        animation.finished.connect(finished)
        self._button_animations[key] = animation
        animation.start()

    def press_button(self, button: QAbstractButton) -> None:
        # Immediate 45% compression remains visible even on a very fast click.
        button.setProperty("khcmPressProgress", max(0.45, float(button.property("khcmPressProgress") or 0.0)))
        button.update()
        self._animate_button(button, "khcmPressProgress", 1.0, self.PRESS_MS, QEasingCurve.OutCubic)

    def release_button(self, button: QAbstractButton) -> None:
        button.setProperty("khcmPressProgress", max(0.82, float(button.property("khcmPressProgress") or 0.0)))
        button.update()
        self._animate_button(button, "khcmPressProgress", 0.0, self.RELEASE_MS, QEasingCurve.OutBack)

    def hover_button(self, button: QAbstractButton, entered: bool) -> None:
        self._animate_button(
            button,
            "khcmHoverProgress",
            1.0 if entered else 0.0,
            self.HOVER_IN_MS if entered else self.HOVER_OUT_MS,
            QEasingCurve.OutCubic,
        )

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
            elif event.type() == QEvent.Enter:
                self.hover_button(watched, True)
            elif event.type() == QEvent.Leave:
                self.hover_button(watched, False)
        elif isinstance(watched, QDialog) and event.type() == QEvent.Show:
            self._fade_dialog(watched)
        return super().eventFilter(watched, event)
