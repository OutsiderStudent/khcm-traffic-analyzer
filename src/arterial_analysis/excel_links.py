"""Microsoft Excel의 저장된 셀값을 읽는 얇은 COM 연결 계층."""

from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".xlsb"}


def _excel_modules():
    import pythoncom
    import win32com.client
    return pythoncom, win32com.client


def normalize_cell(address: str) -> str:
    return str(address or "").replace("$", "").strip().upper()


def list_sheets(path: str) -> list[str]:
    pythoncom, client = _excel_modules(); pythoncom.CoInitialize()
    excel = None; workbook = None
    try:
        excel = client.DispatchEx("Excel.Application")
        excel.Visible = False; excel.DisplayAlerts = False; excel.AskToUpdateLinks = False
        workbook = excel.Workbooks.Open(str(Path(path).resolve()), UpdateLinks=0, ReadOnly=True)
        return [str(sheet.Name) for sheet in workbook.Worksheets]
    finally:
        if workbook is not None: workbook.Close(SaveChanges=False)
        if excel is not None: excel.Quit()
        pythoncom.CoUninitialize()


def read_saved_cell(path: str, sheet: str, address: str):
    """디스크에 저장된 통합문서에서 단일 셀값을 읽는다."""
    result = read_saved_cells(path, sheet, [address])[normalize_cell(address)]
    if result[2]: raise ValueError(result[2])
    return result[0], result[1]


def read_saved_cells(path: str, sheet: str, addresses: list[str]):
    """통합문서를 한 번만 열어 같은 시트의 여러 셀을 일괄 읽는다."""
    pythoncom, client = _excel_modules(); pythoncom.CoInitialize()
    excel = None; workbook = None
    try:
        excel = client.DispatchEx("Excel.Application")
        excel.Visible = False; excel.DisplayAlerts = False; excel.AskToUpdateLinks = False
        workbook = excel.Workbooks.Open(str(Path(path).resolve()), UpdateLinks=0, ReadOnly=True)
        worksheet=workbook.Worksheets(str(sheet));results={}
        for address in dict.fromkeys(normalize_cell(a) for a in addresses):
            try:
                target=worksheet.Range(address)
                if bool(target.MergeCells):target=target.MergeArea.Cells(1,1)
                value=target.Value2
                if value is None or isinstance(value,(str,bool)):raise ValueError("원본 셀이 비어 있거나 숫자가 아닙니다.")
                results[address]=(int(round(float(value))),normalize_cell(str(target.Address)),"")
            except Exception as exc:results[address]=(None,address,str(exc))
        return results
    finally:
        if workbook is not None: workbook.Close(SaveChanges=False)
        if excel is not None: excel.Quit()
        pythoncom.CoUninitialize()


def open_and_activate(path: str, sheet: str = "") -> None:
    """기존 Excel을 재사용해 원본 파일을 열고 앞으로 가져온다."""
    pythoncom, client = _excel_modules(); pythoncom.CoInitialize()
    excel = client.Dispatch("Excel.Application")
    full = str(Path(path).resolve()).lower()
    workbook = next((book for book in excel.Workbooks if str(book.FullName).lower() == full), None)
    if workbook is None: workbook = excel.Workbooks.Open(str(Path(path).resolve()), UpdateLinks=0, ReadOnly=False)
    excel.Visible = True; workbook.Activate()
    if sheet: workbook.Worksheets(str(sheet)).Activate()
    excel.WindowState = -4143
    pythoncom.CoUninitialize()


def active_selection() -> tuple[str, str, str, bool]:
    """활성 Excel 선택의 파일, 시트, 셀 주소, 저장 여부를 반환한다."""
    pythoncom, client = _excel_modules(); pythoncom.CoInitialize()
    try:
        excel = client.GetActiveObject("Excel.Application")
        workbook = excel.ActiveWorkbook; sheet = excel.ActiveSheet; target = excel.Selection
        if workbook is None or sheet is None or target is None: raise RuntimeError("Excel에서 셀을 선택해 주세요.")
        if bool(target.MergeCells): target = target.MergeArea.Cells(1, 1)
        return str(workbook.FullName), str(sheet.Name), normalize_cell(str(target.Address)), bool(workbook.Saved)
    finally:
        pythoncom.CoUninitialize()
