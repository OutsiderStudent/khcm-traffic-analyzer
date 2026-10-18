"""Measure saved-value reads with/without reuse using a synthetic workbook."""
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from openpyxl import Workbook

from arterial_analysis.excel_links import clear_saved_workbook_cache, read_saved_expressions


def main():
    with TemporaryDirectory() as folder:
        path=Path(folder)/"synthetic.xlsx"
        book=Workbook();sheet=book.active;sheet.title="Traffic"
        for row in range(1,5001):
            sheet.append([row*10+column for column in range(12)])
        sheet["M1"]=.945;book.save(path);book.close()
        requests=[("volume",[f"A{row}:C{row}" for row in range(1,101)]),("phf",["M1"])]
        timings={};outputs={}
        for mode in ("reopen","reuse"):
            clear_saved_workbook_cache();start=perf_counter();values=[]
            for _ in range(5):
                for kind,expressions in requests:
                    if mode=="reopen":clear_saved_workbook_cache()
                    values.append(read_saved_expressions(str(path),"Traffic",expressions,kind))
            timings[mode]=perf_counter()-start;outputs[mode]=values
        assert outputs["reopen"]==outputs["reuse"]
        print(f"ROWS=5000 COLUMNS=13 REFRESHES=5")
        print(f"REOPEN_SECONDS={timings['reopen']:.3f}")
        print(f"REUSE_SECONDS={timings['reuse']:.3f}")
        print(f"SPEEDUP={timings['reopen']/timings['reuse']:.2f}x")
        print("VALUES_IDENTICAL=True")
        clear_saved_workbook_cache()


if __name__=="__main__":main()
