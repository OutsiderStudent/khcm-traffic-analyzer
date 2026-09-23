"""Render the connected-tab layouts for visual release QA."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from arterial_analysis.app_fast import FAST_STYLE, MainWindow


OUTPUT = Path(__file__).resolve().parent / "tab-layout"


def save(window: MainWindow, name: str) -> None:
    QApplication.processEvents()
    window.grab().save(str(OUTPUT / f"{name}.png"))


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(FAST_STYLE)
    window = MainWindow()
    window.resize(1224, 756)
    window.project.ensure_tab("사업 미시행시", 2033)
    page = window.workflow.input
    page.refresh_tabs(("현황", 2026))
    table = page.external
    values = {1: "비슬로", 2: "1", 3: "간경교차로", 5: "2", 6: "화원옥포IC네거리", 7: "550", 8: "3", 10: "100", 11: "50", 12: "1,648", 13: "0.95"}
    table.blockSignals(True)
    for column, value in values.items():
        table.item(0, column).setText(value)
    table.blockSignals(False)
    page.commit_row(table, 0, 13)
    window.show()
    save(window, "input")
    page.toggle_optional()
    QApplication.processEvents()
    table.scrollToItem(table.item(0, 20))
    save(window, "optional-colors")
    page.toggle_optional()
    window.workflow.go(1)
    save(window, "results")
    window.workflow.go(2)
    save(window, "details")
    window.tabs.setCurrentIndex(1)
    save(window, "guidelines")
    window.dirty = False
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
