"""GitHub Releases를 이용한 업데이트 확인·검증·자동 설치."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget


REPOSITORY = "OutsiderStudent/khcm-traffic-analyzer"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases/latest"
UPDATE_MANIFEST_URL = f"https://github.com/{REPOSITORY}/releases/latest/download/update.json"
ASSET_PREFIX = "KHCM-Traffic-Analyzer"
CHECK_TITLE = "업데이트 확인"


def _native_windows_machine() -> str:
    """Detect the native Windows CPU even when this process is emulated."""
    if os.name != "nt":
        return ""
    try:
        import ctypes

        process_machine = ctypes.c_ushort()
        native_machine = ctypes.c_ushort()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        is_wow64_process2 = kernel32.IsWow64Process2
        is_wow64_process2.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ushort),
            ctypes.POINTER(ctypes.c_ushort),
        ]
        is_wow64_process2.restype = ctypes.c_bool
        if is_wow64_process2(kernel32.GetCurrentProcess(), ctypes.byref(process_machine), ctypes.byref(native_machine)):
            return {0xAA64: "ARM64", 0x8664: "AMD64"}.get(native_machine.value, "")
    except (AttributeError, OSError):
        pass
    return ""


def release_architecture(machine: str | None = None) -> str:
    """Return the release asset architecture, preferring the native Windows CPU."""
    if machine is None:
        # An x64 process running under Windows-on-Arm reports AMD64 through
        # platform.machine(). IsWow64Process2 exposes the native CPU so the
        # updater can migrate that installation to the native ARM64 build.
        machine = _native_windows_machine() or os.environ.get("PROCESSOR_ARCHITEW6432") or platform.machine()
    normalized = str(machine or "").strip().lower().replace("-", "_")
    return "arm64" if normalized in {"arm64", "aarch64", "arm_64"} else "x64"


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


def parse_release(payload: bytes | str, architecture: str | None = None) -> ReleaseInfo:
    data = json.loads(payload)
    architecture = architecture or release_architecture()
    if "tag_name" not in data:
        version_value = str(data.get("version", ""))
        parsed = version_tuple(version_value)
        if parsed is None:
            raise ValueError("최신 릴리스의 버전 형식이 올바르지 않습니다.")
        version = ".".join(str(part) for part in parsed)
        assets = data.get("assets") or {}
        asset = assets.get(architecture) if isinstance(assets, dict) else None
        if not isinstance(asset, dict):
            raise ValueError(f"릴리스에 {architecture} 업데이트 파일이 없습니다.")
        return ReleaseInfo(
            version=version,
            title=str(data.get("title") or f"KHCM Traffic Analyzer v{version}"),
            notes=str(data.get("notes") or "변경사항이 제공되지 않았습니다."),
            page_url=str(data.get("page_url") or RELEASES_URL),
            asset_url=str(asset.get("url") or ""),
            digest=str(asset.get("digest") or ""),
            size=int(asset.get("size") or 0),
        )
    tag = str(data.get("tag_name", ""))
    parsed = version_tuple(tag)
    if parsed is None:
        raise ValueError("최신 릴리스의 버전 형식이 올바르지 않습니다.")
    version = ".".join(str(part) for part in parsed)
    expected_name = f"{ASSET_PREFIX}_v{version}_{architecture}.exe"
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
        self.architecture = release_architecture()
        self.parent_widget = parent
        self.network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._manual = False
        self._download_file = None
        self._download_path: Path | None = None
        self._release: ReleaseInfo | None = None
        self._progress: QProgressDialog | None = None
        self._checking: QProgressDialog | None = None

    def check(self, manual: bool = False) -> None:
        if self._reply is not None:
            if manual and self._progress is None and self._checking is None:
                self._manual = True
                self._show_checking()
            return
        self._manual = manual
        request = QNetworkRequest(QUrl(UPDATE_MANIFEST_URL))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        request.setRawHeader(b"Accept", b"application/json")
        request.setRawHeader(b"User-Agent", f"KHCM-Traffic-Analyzer/{self.current_version}".encode("ascii"))
        request.setTransferTimeout(15_000)
        self._reply = self.network.get(request)
        self._reply.finished.connect(self._check_finished)
        if manual:
            self._show_checking()

    def _show_checking(self) -> None:
        self._checking = QProgressDialog("업데이트 확인 중…", "취소", 0, 0, self.parent_widget)
        self._checking.setWindowTitle(CHECK_TITLE)
        self._checking.canceled.connect(self._reply.abort)
        self._checking.show()

    def _check_finished(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        if self._checking is not None:
            self._checking.hide()
            self._checking.deleteLater()
            self._checking = None
        try:
            if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
                return
            if reply.error() != QNetworkReply.NetworkError.NoError:
                status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                detail = f" (오류 코드: {status})" if status else ""
                raise RuntimeError("업데이트를 확인할 수 없습니다. 인터넷 연결을 확인해 주세요." + detail)
            release = parse_release(bytes(reply.readAll()), self.architecture)
            current = version_tuple(self.current_version)
            latest = version_tuple(release.version)
            if current is None or latest is None:
                raise ValueError("버전을 비교할 수 없습니다.")
            if latest <= current:
                if self._manual:
                    QMessageBox.information(self.parent_widget, CHECK_TITLE, "업데이트가 없습니다.")
                return
            self._offer(release)
        except (ValueError, RuntimeError, json.JSONDecodeError) as error:
            if self._manual:
                QMessageBox.warning(self.parent_widget, CHECK_TITLE, str(error))
        finally:
            reply.deleteLater()

    def _offer(self, release: ReleaseInfo) -> None:
        box = QMessageBox(self.parent_widget)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(CHECK_TITLE)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(f"새 버전이 있습니다. (v{release.version})")
        notes = release.notes.strip()
        if len(notes) > 240:
            notes = notes[:240].rstrip() + "…"
        box.setInformativeText(notes)
        install = box.addButton("업데이트", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is install:
            self._start_download(release)

    def _start_download(self, release: ReleaseInfo) -> None:
        if not release.asset_url:
            QMessageBox.warning(self.parent_widget, "업데이트", "다운로드 주소를 확인할 수 없습니다.")
            return
        update_dir = Path(tempfile.gettempdir()) / f"{ASSET_PREFIX}-updates"
        update_dir.mkdir(parents=True, exist_ok=True)
        self._download_path = update_dir / f"{ASSET_PREFIX}_v{release.version}_{self.architecture}.exe.part"
        self._download_file = self._download_path.open("wb")
        self._release = release
        request = QNetworkRequest(QUrl(release.asset_url))
        request.setRawHeader(b"User-Agent", f"KHCM-Traffic-Analyzer/{self.current_version}".encode("ascii"))
        request.setTransferTimeout(120_000)
        self._reply = self.network.get(request)
        self._reply.readyRead.connect(self._write_download_data)
        self._reply.downloadProgress.connect(self._download_progress)
        self._reply.finished.connect(self._download_finished)
        self._progress = QProgressDialog("다운로드 중…", "취소", 0, max(0, release.size), self.parent_widget)
        self._progress.setWindowTitle(CHECK_TITLE)
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
            self._progress.hide()
            self._progress.deleteLater()
            self._progress = None
        try:
            if reply is not None and reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
                if self._download_path is not None:
                    self._download_path.unlink(missing_ok=True)
                return
            if reply is None or reply.error() != QNetworkReply.NetworkError.NoError:
                raise RuntimeError("다운로드하지 못했습니다. 인터넷 연결을 확인해 주세요.")
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
            raise ValueError("업데이트 파일을 확인할 수 없습니다.")
        expected = release.digest.split(":", 1)[1].lower()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest().lower() != expected:
            raise ValueError("다운로드한 파일을 확인할 수 없습니다. 다시 시도해 주세요.")

    def _install_download(self, source: Path, release: ReleaseInfo) -> None:
        if not getattr(sys, "frozen", False):
            QDesktopServices.openUrl(QUrl(release.page_url))
            source.unlink(missing_ok=True)
            return
        current = Path(sys.executable).resolve()
        box = QMessageBox(self.parent_widget)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("다운로드 완료")
        box.setText("프로그램을 다시 시작할까요?")
        yes = box.addButton("예", QMessageBox.ButtonRole.YesRole)
        no = box.addButton("아니요", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(yes)
        box.setEscapeButton(no)
        box.exec()
        if box.clickedButton() is not yes:
            source.unlink(missing_ok=True)
            return
        confirm_discard = getattr(self.parent_widget, "confirm_discard", None)
        if callable(confirm_discard) and not confirm_discard():
            source.unlink(missing_ok=True)
            return
        downloads = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation))
        fallback = downloads / f"{ASSET_PREFIX}_v{release.version}_{self.architecture}.exe"
        script = Path(tempfile.gettempdir()) / f"{ASSET_PREFIX}-updater.ps1"
        script.write_text(update_helper_script(), encoding="utf-8-sig")
        started, _ = QProcess.startDetached(
            "powershell.exe",
            ["-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script), str(os.getpid()), str(current), str(source), str(fallback)],
        )
        if not started:
            raise RuntimeError("업데이트 도우미를 실행할 수 없습니다.")
        QApplication.quit()
