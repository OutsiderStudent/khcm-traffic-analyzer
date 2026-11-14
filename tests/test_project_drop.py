import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QMimeData,QUrl,QPoint,QPointF,Qt
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from arterial_analysis.app_fast import MainWindow,project_drop_path
from arterial_analysis.project import ArterialProject
from arterial_analysis.engine_2026 import official_example

APP=QApplication.instance() or QApplication([])


class ProjectDropTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/"한글 분석 파일.ARA1"
        ArterialProject(name="드롭 확인",analysis_edition="2026",corridors_2026=[official_example().to_dict()]).save(self.path)
        self.window=MainWindow();self.window.show();APP.processEvents()

    def tearDown(self):
        self.window.deleteLater();APP.processEvents();self.temp.cleanup()

    def mime(self,urls=None):
        m=QMimeData();m.setUrls(urls or [QUrl.fromLocalFile(str(self.path))]);return m

    def drop(self,target=None):
        target=target or self.window;m=self.mime()
        enter=QDragEnterEvent(QPoint(5,5),Qt.CopyAction,m,Qt.LeftButton,Qt.NoModifier)
        APP.sendEvent(target,enter);self.assertTrue(enter.isAccepted())
        event=QDropEvent(QPointF(5,5),Qt.CopyAction,m,Qt.LeftButton,Qt.NoModifier)
        APP.sendEvent(target,event);return event

    def test_drop_opens_project_and_edition(self):
        event=self.drop();self.assertTrue(event.isAccepted())
        self.assertEqual(self.window.project.name,"드롭 확인")
        self.assertEqual(self.window.project.analysis_edition,"2026")
        self.assertTrue(self.window.tabs.isTabVisible(self.window.beta_index))
        self.assertTrue(self.path.exists())

    def test_drop_over_text_editor_opens_instead_of_inserting_path(self):
        self.assertTrue(self.drop(self.window.workflow.input.formula).isAccepted())
        self.assertEqual(self.window.project.name,"드롭 확인")

    def test_2013_drop_over_table_viewport(self):
        ArterialProject(name="2013 파일").save(self.path)
        self.assertTrue(self.drop(self.window.workflow.input.external.viewport()).isAccepted())
        self.assertEqual(self.window.project.analysis_edition,"2013")
        self.assertEqual(self.window.project.name,"2013 파일")

    def test_cancel_keeps_unsaved_project(self):
        original=self.window.project;original.name="미저장 변경";self.window.mark_dirty()
        with patch.object(self.window,"confirm_discard",return_value=False) as confirm:
            self.assertFalse(self.drop().isAccepted());confirm.assert_called_once()
        self.assertIs(self.window.project,original);self.assertTrue(self.window.dirty)

    def test_save_before_drop_writes_old_project(self):
        saved=Path(self.temp.name)/"이전.ara1";self.window.path=str(saved)
        self.window.project.name="저장할 변경";self.window.mark_dirty()
        with patch.object(QMessageBox,"exec",return_value=QMessageBox.Save):
            self.assertTrue(self.drop().isAccepted())
        self.assertEqual(ArterialProject.load(saved).name,"저장할 변경")

    def test_invalid_file_keeps_current_project(self):
        original=self.window.project;self.path.write_text("not json",encoding="utf-8")
        with patch.object(QMessageBox,"critical") as error:
            self.assertFalse(self.drop().isAccepted());error.assert_called_once()
        self.assertIs(self.window.project,original)

    def test_rejects_multiple_remote_missing_and_nonproject_files(self):
        for urls in ([QUrl.fromLocalFile(str(self.path))]*2,[QUrl("https://example.com/a.ara1")],
                     [QUrl.fromLocalFile(str(self.path.with_suffix('.xlsx')))],
                     [QUrl.fromLocalFile(str(self.path.parent/'missing.ara1'))]):
            self.assertIsNone(project_drop_path(self.mime(urls)))
        m=QMimeData();m.setText("text");self.assertIsNone(project_drop_path(m))
