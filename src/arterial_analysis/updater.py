"""GitHub Releases를 이용한 업데이트 확인·검증·자동 설치."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget


REPOSITORY = "OutsiderStudent/khcm-traffic-analyzer"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases/latest"
ASSET_PREFIX = "KHCM-Traffic-Analyzer"


def update_helper_script() -> str:
    """실행 중인 EXE가 종료된 뒤 같은 경로를 보존하며 교체한다."""
    return (
        "param([int]$OldPid,[string]$OldExe,[string]$NewExe,[string]$FallbackExe)\n"
        "Wait-Process -Id $OldPid -ErrorAction SilentlyContinue\n"
        "# The replacement EXE is an independent PyInstaller process, not a child using the old _MEI directory.\n"
        "$env:PYINSTALLER_RESET_ENVIRONMENT = '1'\n"
        "Remove-Item Env:_PYI_APPLICATION_HOME_DIR -ErrorAction SilentlyContinue\n"
        "Remove-Item Env:_PYI_ARCHIVE_FILE -ErrorAction SilentlyContinue\n"
        "Remove-Item Env:_PYI_PARENT_PROCESS_LEVEL -ErrorAction SilentlyContinue\n"
        "Remove-Item Env:_PYI_SPLASH_IPC -ErrorAction SilentlyContinue\n"
        "Remove-Item Env:_MEIPASS2 -ErrorAction SilentlyContinue\n"
        "$Installed = $false\n"
        "for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {\n"
        "  try { Copy-Item -LiteralPath $NewExe -Destination $OldExe -Force -ErrorAction Stop; $Installed = $true; break }\n"
        "  catch { Start-Sleep -Milliseconds 250 }\n"
        "}\n"
        "if ($Installed) {\n"
        "  Remove-Item -LiteralPath $NewExe -Force -ErrorAction SilentlyContinue\n"
        "  Start-Process -FilePath $OldExe\n"
        "} else {\n"
        "  Copy-Item -LiteralPath $NewExe -Destination $FallbackExe -Force\n"
        "  Remove-Item -LiteralPath $NewExe -Force -ErrorAction SilentlyContinue\n"
        "  Start-Process -FilePath $FallbackExe\n"
        "}\n"
    )


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
    asset_url: str
    digest: str
    size: int


def parse_release(payload: bytes | str) -> ReleaseInfo:
    data = json.loads(payload)
    tag = str(data.get("tag_name", ""))
    parsed = version_tuple(tag)
    if parsed is None:
        raise ValueError("최신 릴리스의 버전 형식이 올바르지 않습니다.")
    version = ".".join(str(part) for part in parsed)
    expected_name = f"{ASSET_PREFIX}_v{version}.exe"
    asset = next((item for item in data.get("assets", []) if item.get("name") == expected_name), None)
    if asset is None:
        raise ValueError(f"릴리스에 {expected_name} 파일이 없습니다.")
    return ReleaseInfo(
        version=version,
        title=str(data.get("name") or tag),
        notes=str(data.get("body") or "변경사항이 제공되지 않았습니다."),
        page_url=str(data.get("html_url") or RELEASES_URL),
        asset_url=str(asset.get("browser_download_url") or ""),
        digest=str(asset.get("digest") or ""),
        size=int(asset.get("size") or 0),
    )


class UpdateController(QObject):
    """최신 릴리스를 내려받아 검증하고 안전하게 재시작한다."""

    def __init__(self, current_version: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.current_version = current_version
        self.parent_widget = parent
        self.network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._manual = False
        self._download_file = None
        self._download_path: Path | None = None
        self._release: ReleaseInfo | None = None
        self._progress: QProgressDialog | None = None

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
        self._reply.finished.connect(self._check_finished)

    def _check_finished(self) -> None:
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
                    QMessageBox.information(self.parent_widget, "업데이트", f"현재 v{self.current_version}이 최신 버전입니다.")
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
        box.setWindowTitle("업데이트")
        box.setText(f"KHCM Traffic Analyzer v{release.version} 업데이트가 있습니다.")
        notes = release.notes.strip()
        if len(notes) > 900:
            notes = notes[:900].rstrip() + "…"
        box.setInformativeText(notes)
        install = box.addButton("다운로드 및 업데이트", QMessageBox.ButtonRole.AcceptRole)
        page = box.addButton("GitHub 릴리스", QMessageBox.ButtonRole.ActionRole)
        box.addButton("나중에", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is install:
            self._start_download(release)
        elif box.clickedButton() is page:
            QDesktopServices.openUrl(QUrl(release.page_url))

    def _start_download(self, release: ReleaseInfo) -> None:
        if not release.asset_url:
            QMessageBox.warning(self.parent_widget, "업데이트", "다운로드 주소를 확인할 수 없습니다.")
            return
        update_dir = Path(tempfile.gettempdir()) / f"{ASSET_PREFIX}-updates"
        update_dir.mkdir(parents=True, exist_ok=True)
        self._download_path = update_dir / f"{ASSET_PREFIX}_v{release.version}.exe.part"
        self._download_file = self._download_path.open("wb")
        self._release = release
        request = QNetworkRequest(QUrl(release.asset_url))
        request.setRawHeader(b"User-Agent", f"KHCM-Traffic-Analyzer/{self.current_version}".encode("ascii"))
        request.setTransferTimeout(120_000)
        self._reply = self.network.get(request)
        self._reply.readyRead.connect(self._write_download_data)
        self._reply.downloadProgress.connect(self._download_progress)
        self._reply.finished.connect(self._download_finished)
        self._progress = QProgressDialog("업데이트를 다운로드하고 있습니다.", "취소", 0, max(0, release.size), self.parent_widget)
        self._progress.setWindowTitle("업데이트")
        self._progress.setWindowModality(self.parent_widget.windowModality())
        self._progress.canceled.connect(self._reply.abort)
        self._progress.show()

    def _write_download_data(self) -> None:
        if self._reply is not None and self._download_file is not None:
            self._download_file.write(bytes(self._reply.readAll()))

    def _download_progress(self, received: int, total: int) -> None:
        if self._progress is not None:
            self._progress.setMaximum(max(0, total))
            self._progress.setValue(received)

    def _download_finished(self) -> None:
        reply = self._reply
        if reply is not None and self._download_file is not None:
            self._download_file.write(bytes(reply.readAll()))
        self._reply = None
        if self._download_file is not None:
            self._download_file.close()
            self._download_file = None
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        try:
            if reply is None or reply.error() != QNetworkReply.NetworkError.NoError:
                raise RuntimeError(reply.errorString() if reply is not None else "다운로드 응답이 없습니다.")
            if self._download_path is None or self._release is None:
                raise RuntimeError("다운로드 파일 정보가 없습니다.")
            self._verify_download(self._download_path, self._release)
            self._install_download(self._download_path, self._release)
        except (OSError, RuntimeError, ValueError) as error:
            if self._download_path is not None:
                self._download_path.unlink(missing_ok=True)
            QMessageBox.warning(self.parent_widget, "업데이트 실패", str(error))
        finally:
            if reply is not None:
                reply.deleteLater()

    @staticmethod
    def _verify_download(path: Path, release: ReleaseInfo) -> None:
        if not release.digest.lower().startswith("sha256:"):
            raise ValueError("릴리스에 SHA-256 검증값이 없어 업데이트를 중단했습니다.")
        expected = release.digest.split(":", 1)[1].lower()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != expected:
            raise ValueError("다운로드한 파일의 SHA-256 검증에 실패했습니다.")

    def _install_download(self, source: Path, release: ReleaseInfo) -> None:
        if not getattr(sys, "frozen", False):
            QDesktopServices.openUrl(QUrl(release.page_url))
            QMessageBox.information(self.parent_widget, "업데이트", "개발 실행 중이므로 GitHub 릴리스를 열었습니다.")
            return
        current = Path(sys.executable).resolve()
        choice = QMessageBox.question(
            self.parent_widget,
            "업데이트 준비 완료",
            f"v{release.version} 다운로드와 검증이 완료되었습니다.\n지금 재시작하여 업데이트할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if choice != QMessageBox.StandardButton.Yes:
            source.unlink(missing_ok=True)
            return
        confirm_discard = getattr(self.parent_widget, "confirm_discard", None)
        if callable(confirm_discard) and not confirm_discard():
            source.unlink(missing_ok=True)
            QMessageBox.information(self.parent_widget, "업데이트", "업데이트 재시작을 취소했습니다.")
            return
        downloads = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation))
        fallback = downloads / f"{ASSET_PREFIX}_v{release.version}.exe"
        script = Path(tempfile.gettempdir()) / f"{ASSET_PREFIX}-updater.ps1"
        script.write_text(update_helper_script(), encoding="utf-8-sig")
        started, _ = QProcess.startDetached(
            "powershell.exe",
            ["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script), str(os.getpid()), str(current), str(source), str(fallback)],
        )
        if not started:
            raise RuntimeError("업데이트 도우미를 실행할 수 없습니다.")
        QApplication.quit()
