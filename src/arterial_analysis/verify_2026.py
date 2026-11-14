"""Opt-in packaged beta verification: --verify-2026 OUTPUT_DIRECTORY."""
import json
import os
from pathlib import Path


def verify(output_directory):
    os.environ["QT_QPA_PLATFORM"]="offscreen"
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QMimeData,QUrl,QPoint,QPointF,Qt
    from PySide6.QtGui import QDragEnterEvent,QDropEvent
    from .app_fast import MainWindow, APP_VERSION
    from .engine_2026 import official_example, analyze_corridor
    from .project import ArterialProject
    output=Path(output_directory);output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);window=MainWindow()
    project=ArterialProject(analysis_edition="2026",corridors_2026=[official_example(i).to_dict() for i in (1,2,3)])
    sample=output/"2026_편람예제_검증.ara1";project.save(sample)
    mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(sample.resolve()))])
    target=window.workflow.input.formula
    enter=QDragEnterEvent(QPoint(5,5),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
    app.sendEvent(target,enter);assert enter.isAccepted(), "File drag rejected"
    drop=QDropEvent(QPointF(5,5),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
    app.sendEvent(target,drop);assert drop.isAccepted(), "File drop failed"
    assert window.project.analysis_edition=="2026"
    assert [r.los for r in window.project.analyze_all()]==["D","D","C"], "Project mode dispatch failed"
    window.resize(1224,850);window.show();app.processEvents()
    page=window.beta_page
    page.tabs.setCurrentIndex(0);app.processEvents();window.grab().save(str(output/"2026-scope.png"))
    page.tabs.setCurrentIndex(1);app.processEvents();window.grab().save(str(output/"2026-input.png"))
    checked=[]
    for i,(speed,grade) in enumerate(((20.0,"D"),(20.1,"D"),(26.3,"C"))):
        page.selector.setCurrentIndex(i)
        assert page.analyze(), "UI analysis failed"
        r=analyze_corridor(page.current())
        assert round(r.speed_kmh,1)==speed and r.los==grade
        assert f"{speed:.1f}" in page.result.toPlainText()
        checked.append({"example":i+1,"speed":r.speed_kmh,"los":r.los})
        (output/f"예제{i+1}_분석결과.html").write_text(page.result.toHtml(),encoding="utf-8")
    app.processEvents();window.grab().save(str(output/"2026-result.png"))
    window.resize(880,600);page.tabs.setCurrentIndex(1);app.processEvents()
    window.grab().save(str(output/"2026-narrow.png"))
    window.project.analysis_edition="2013";window.sync_edition();app.processEvents()
    assert window.tabs.isTabVisible(0) and not window.tabs.isTabVisible(window.beta_index)
    result={"version":APP_VERSION,"packaged":bool(getattr(__import__('sys'),'frozen',False)),"examples":checked,
            "project_open":True,"file_drop":True,"edition_switch":True,"render_sizes":[[1224,850],[880,600]]}
    (output/"verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    window.deleteLater();app.processEvents()
    return 0
