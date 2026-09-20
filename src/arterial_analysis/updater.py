"""GitHub Releases 기반의 비차단 업데이트 확인."""

from __future__ import annotations

import json
from dataclasses import dataclass

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QMessageBox, QWidget


REPOSITORY = "OutsiderStudent/khcm-traffic-analyzer"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases/latest"


def version_tuple(value: str) -> tuple[int, int, int] | None:
    parts = value.strip().lstrip("vV").split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    title: str
    notes: str
    page_url: str


def parse_release(payload: bytes | str) -> ReleaseInfo:
    data = json.loads(payload)
    tag = str(data.get("tag_name", ""))
    parsed = version_tuple(tag)
    if parsed is None:
        raise ValueError("최신 릴리스의 버전 형식이 올바르지 않습니다.")
    return ReleaseInfo(
        version=".".join(str(part) for part in parsed),
        title=str(data.get("name") or tag),
        notes=str(data.get("body") or "변경사항이 제공되지 않았습니다."),
        page_url=str(data.get("html_url") or RELEASES_URL),
    )


class UpdateController(QObject):
    """시작 시 조용히, 메뉴에서는 결과를 표시하며 최신 릴리스를 확인한다."""

    def __init__(self, current_version: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.current_version = current_version
        self.parent_widget = parent
        self.network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._manual = False

    def check(self, manual: bool = False) -> None:
        if self._reply is not None:
            if manual:
                QMessageBox.information(self.parent_widget, "업데이트", "이미 업데이트를 확인하고 있습니다.")
            return
        self._manual = manual
        request = QNetworkRequest(QUrl(RELEASE_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", f"KHCM-Traffic-Analyzer/{self.current_version}".encode("ascii"))
        request.setTransferTimeout(15_000)
        self._reply = self.network.get(request)
        self._reply.finished.connect(self._finished)

    def _finished(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                raise RuntimeError(reply.errorString())
            release = parse_release(bytes(reply.readAll()))
            current = version_tuple(self.current_version)
            latest = version_tuple(release.version)
            if current is None or latest is None:
                raise ValueError("버전을 비교할 수 없습니다.")
            if latest <= current:
                if self._manual:
                    QMessageBox.information(
                        self.parent_widget,
                        "업데이트",
                        f"현재 v{self.current_version}이 최신 버전입니다.",
                    )
                return
            self._offer(release)
        except (ValueError, RuntimeError, json.JSONDecodeError) as error:
            if self._manual:
                QMessageBox.warning(self.parent_widget, "업데이트 확인 실패", str(error))
        finally:
            reply.deleteLater()

    def _offer(self, release: ReleaseInfo) -> None:
        box = QMessageBox(self.parent_widget)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("새 버전 안내")
        box.setText(f"KHCM Traffic Analyzer v{release.version}이 출시되었습니다.")
        notes = release.notes.strip()
        if len(notes) > 900:
            notes = notes[:900].rstrip() + "…"
        box.setInformativeText(notes)
        open_page = box.addButton("다운로드 페이지 열기", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_page:
            QDesktopServices.openUrl(QUrl(release.page_url))
