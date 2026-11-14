"""Run once per source tree, then compare the JSON results."""
import json
import os
import statistics
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication
from arterial_analysis import app_fast as ui
from arterial_analysis.engine import analyze_segment
from arterial_analysis.project import ArterialProject


def main():
    if len(sys.argv)==4 and sys.argv[1]=="--compare":
        a,b=[json.loads(Path(path).read_text(encoding="utf-8-sig")) for path in sys.argv[2:]]
        keys=[k for k in ("analysis","existing_analysis","linked_analysis") if k in a or k in b]
        for k in keys:
            assert a[k]==b[k], f"Different: {k}"
        summary={
            "identical_analysis_counts":{k:len(a[k]) if isinstance(a[k],list) else 1 for k in keys},
            "enter_simulated_read_delay_ms":150,
            "runs":[{k:v for k,v in run.items() if k not in keys} for run in (a,b)],
        }
        print(json.dumps(summary,indent=2,ensure_ascii=True))
        return
    app=QApplication([])
    window=ui.MainWindow()
    page=window.workflow.input
    project=page.project
    key=("현황",2026)
    seed=project.rows(*key)[0]
    project.replace_rows(*key,[replace(seed,uid=str(i),comparison_id=str(i),length_km=1.2,lanes=2,cycle_s=120,green_s=50,main_volume=900+i%80,phf=.92,blank_fields=[],end_number=str(i+10),end_name=f"교차로{i}") for i in range(512)])
    page.load_key(key)
    table=page.external
    times=[]
    for i in range(26):
        start=time.perf_counter()
        table.item(0,12).setText(str(1300+i))
        elapsed=(time.perf_counter()-start)*1000
        if i:times.append(elapsed)
    result={"version":ui.APP_VERSION,"rows":512,"trials":len(times),"edit_median_ms":statistics.median(times),"edit_p95_ms":sorted(times)[23]}
    result["analysis"]=[asdict(analyze_segment(row,project.settings)) for row in project.rows(*key)]
    if len(sys.argv)>1:
        existing=ArterialProject.load(sys.argv[1])
        result["existing_analysis"]=[asdict(r) for r in existing.analyze_all()]
    project.tab_info(*key).update(source_path=__file__,source_sheet="Sheet1")
    page._link_table=table;page._link_row=0;page._link_col=12
    page._link_window={"hwnd":123};page._enter_was_down=True;page._link_timer=Mock()
    observed=[]
    def read(*_):
        time.sleep(.15)
        return 1440,"B12"
    with patch.object(ui.ctypes.windll.user32,"IsWindow",return_value=True),patch.object(ui.ctypes.windll.user32,"GetAsyncKeyState",return_value=0),patch.object(ui,"active_selection",return_value=(__file__,"Sheet1","B12",True)),patch.object(ui,"read_saved_cell",side_effect=read),patch.object(ui,"close_link_window"):
        start=time.perf_counter()
        QTimer.singleShot(0,lambda:observed.append((time.perf_counter()-start)*1000))
        page.poll_link();result["enter_handler_ms"]=(time.perf_counter()-start)*1000
        deadline=start+5
        while time.perf_counter()<deadline:
            app.processEvents()
            if table.item(0,12).text()=="1,440":break
            time.sleep(.001)
        assert table.item(0,12).text()=="1,440"
        result["enter_apply_ms"]=(time.perf_counter()-start)*1000
        result["ui_tick_ms"]=observed[0]
        if hasattr(page,"_excel_close_pool"):page._excel_close_pool.waitForDone(2000)
    snapshot=next(row for row in project.rows(*key) if row.uid=="0")
    result["linked_analysis"]=asdict(analyze_segment(snapshot,project.settings))
    print(json.dumps(result,ensure_ascii=True))


if __name__=="__main__":main()
