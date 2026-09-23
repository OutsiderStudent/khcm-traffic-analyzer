"""저장된 Excel 값과 빠른 셀 연결을 다루는 계층."""

from __future__ import annotations

import ctypes
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


SUPPORTED_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".xlsb"}
OPENPYXL_EXTENSIONS = {".xlsx", ".xlsm"}
_CELL = r"\$?[A-Za-z]{1,3}\$?[1-9]\d*"
_TOKEN = re.compile(rf"^(?P<a>{_CELL})(?::(?P<b>{_CELL}))?$")
_EXTERNAL_FORMULA = re.compile(
    r"^=\s*'?(?P<prefix>.*?\[)(?P<book>[^\]]+)\](?P<sheet>[^']+)'?!\$?(?P<column>[A-Za-z]{1,3})\$?(?P<row>[1-9]\d*)$"
)
_LOCAL_FORMULA = re.compile(r"^=\s*'?(?P<sheet>[^']+)'?!\$?(?P<column>[A-Za-z]{1,3})\$?(?P<row>[1-9]\d*)$")


def _excel_modules():
    import pythoncom
    import win32com.client
    return pythoncom, win32com.client


def normalize_cell(address: str) -> str:
    return str(address or "").replace("$", "").strip().upper()


def normalize_expression(expression: str) -> str:
    """H12+H15, H12,H15, 범위와 절대주소를 쉼표 형식으로 통일한다."""
    text=str(expression or "").strip()
    if text.startswith("="):text=text[1:]
    text=text.replace("$","").replace(" ","").replace("+",",").upper()
    if not text:raise ValueError("Excel 셀 주소가 비어 있습니다.")
    tokens=[token for token in text.split(",") if token]
    if not tokens or any(not _TOKEN.fullmatch(token) for token in tokens):
        raise ValueError("셀 주소는 H12, H12:H15 또는 H12,H15 형식으로 입력해 주세요.")
    return ",".join(tokens)


def expression_tokens(expression: str) -> list[tuple[str,str | None]]:
    result=[]
    for token in normalize_expression(expression).split(","):
        match=_TOKEN.fullmatch(token);result.append((normalize_cell(match.group("a")),normalize_cell(match.group("b")) if match.group("b") else None))
    return result


def format_external_formula(path: str, sheet: str, address: str) -> str:
    expression=normalize_expression(address)
    if "," in expression or ":" in expression:return "="+expression
    source=Path(path).resolve();escaped_sheet=str(sheet).replace("'","''");column,row=re.fullmatch(r"([A-Z]{1,3})([1-9]\d*)",expression).groups()
    return f"='{source.parent}\\[{source.name}]{escaped_sheet}'!${column}${row}"


def parse_external_formula(formula: str, default_path: str = "") -> tuple[str,str,str]:
    text=str(formula or "").strip();match=_EXTERNAL_FORMULA.fullmatch(text)
    if match:
        prefix=match.group("prefix")[:-1].replace("''", "'");path=str((Path(prefix)/match.group("book")).resolve());sheet=match.group("sheet").replace("''", "'")
        return path,sheet,normalize_cell(match.group("column")+match.group("row"))
    match=_LOCAL_FORMULA.fullmatch(text)
    if match and default_path:return str(Path(default_path).resolve()),match.group("sheet").replace("''", "'"),normalize_cell(match.group("column")+match.group("row"))
    raise ValueError("전체 외부참조식 또는 셀 주소식을 입력해 주세요.")


def _openpyxl_book(path: str):
    from openpyxl import load_workbook
    source=Path(path).resolve()
    return load_workbook(source,read_only=False,data_only=True,keep_links=False,keep_vba=source.suffix.lower()==".xlsm")


def list_sheets(path: str) -> list[str]:
    if Path(path).suffix.lower() in OPENPYXL_EXTENSIONS:
        workbook=_openpyxl_book(path)
        try:return list(workbook.sheetnames)
        finally:workbook.close()
    pythoncom,client=_excel_modules();pythoncom.CoInitialize();excel=workbook=None
    try:
        excel=client.DispatchEx("Excel.Application");excel.Visible=False;excel.DisplayAlerts=False;excel.AskToUpdateLinks=False
        workbook=excel.Workbooks.Open(str(Path(path).resolve()),UpdateLinks=0,ReadOnly=True)
        return [str(sheet.Name) for sheet in workbook.Worksheets]
    finally:
        if workbook is not None:workbook.Close(SaveChanges=False)
        if excel is not None:excel.Quit()
        pythoncom.CoUninitialize()


def _openpyxl_addresses(worksheet,expression: str) -> list[str]:
    from openpyxl.utils import get_column_letter
    from openpyxl.utils.cell import range_boundaries
    seen=set();result=[]
    for first,last in expression_tokens(expression):
        token=first+(":"+last if last else "");min_col,min_row,max_col,max_row=range_boundaries(token)
        for row in range(min_row,max_row+1):
            if worksheet.row_dimensions[row].hidden:continue
            for col in range(min_col,max_col+1):
                if worksheet.column_dimensions[get_column_letter(col)].hidden:continue
                coord=f"{get_column_letter(col)}{row}"
                for merged in worksheet.merged_cells.ranges:
                    if coord in merged:coord=f"{get_column_letter(merged.min_col)}{merged.min_row}";break
                if coord not in seen:seen.add(coord);result.append(coord)
                if len(result)>10000:raise ValueError("한 연결식은 화면에 보이는 셀 10,000개까지만 사용할 수 있습니다.")
    return result


def _coerce_numeric(value,address: str) -> float:
    if value is None:return 0.0
    if isinstance(value,bool) or isinstance(value,str):raise ValueError(f"{address}: 저장된 숫자값이 아닙니다.")
    try:return float(value)
    except (TypeError,ValueError):raise ValueError(f"{address}: 저장된 숫자값이 아닙니다.")


def _round_integer(value: float) -> int:return int(Decimal(str(value)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
def _round_phf(value: float) -> float:return float(Decimal(str(value)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP))


def read_saved_expressions(path: str,sheet: str,expressions: list[str],kind: str="volume"):
    """주소식들을 통합문서 한 번 열기로 읽는다. volume은 각 셀 반올림 후 합산한다."""
    normalized=list(dict.fromkeys(normalize_expression(item) for item in expressions));results={}
    if Path(path).suffix.lower() in OPENPYXL_EXTENSIONS:
        workbook=_openpyxl_book(path)
        try:
            if str(sheet) not in workbook.sheetnames:raise ValueError(f"'{sheet}' 시트를 찾을 수 없습니다.")
            worksheet=workbook[str(sheet)]
            for expression in normalized:
                try:
                    addresses=_openpyxl_addresses(worksheet,expression)
                    if kind=="phf" and len(addresses)!=1:raise ValueError("PHF는 Excel 셀 하나만 연결할 수 있습니다.")
                    numbers=[_coerce_numeric(worksheet[address].value,address) for address in addresses]
                    if kind=="phf":
                        value=_round_phf(numbers[0])
                        if not 0<value<=1:raise ValueError("PHF는 0보다 크고 1.00 이하여야 합니다.")
                    else:
                        if any(number<0 for number in numbers):raise ValueError("교통량에는 음수를 사용할 수 없습니다.")
                        rounded=[_round_integer(number) for number in numbers]
                        value=sum(rounded)
                    results[expression]=(value,expression,"")
                except Exception as exc:results[expression]=(None,expression,str(exc))
            return results
        finally:workbook.close()
    pythoncom,client=_excel_modules();pythoncom.CoInitialize();excel=workbook=None
    try:
        excel=client.DispatchEx("Excel.Application");excel.Visible=False;excel.DisplayAlerts=False;excel.AskToUpdateLinks=False
        workbook=excel.Workbooks.Open(str(Path(path).resolve()),UpdateLinks=0,ReadOnly=True);worksheet=workbook.Worksheets(str(sheet))
        for expression in normalized:
            try:
                addresses=[];seen=set()
                for first,last in expression_tokens(expression):
                    target=worksheet.Range(first+(":"+last if last else ""))
                    for cell in target.Cells:
                        if bool(cell.EntireRow.Hidden) or bool(cell.EntireColumn.Hidden):continue
                        if bool(cell.MergeCells):cell=cell.MergeArea.Cells(1,1)
                        address=normalize_cell(str(cell.Address))
                        if address not in seen:seen.add(address);addresses.append(address)
                        if len(addresses)>10000:raise ValueError("한 연결식은 화면에 보이는 셀 10,000개까지만 사용할 수 있습니다.")
                if kind=="phf" and len(addresses)!=1:raise ValueError("PHF는 Excel 셀 하나만 연결할 수 있습니다.")
                numbers=[_coerce_numeric(worksheet.Range(address).Value2,address) for address in addresses]
                if kind=="phf":
                    value=_round_phf(numbers[0])
                    if not 0<value<=1:raise ValueError("PHF는 0보다 크고 1.00 이하여야 합니다.")
                else:
                    if any(number<0 for number in numbers):raise ValueError("교통량에는 음수를 사용할 수 없습니다.")
                    rounded=[_round_integer(number) for number in numbers]
                    value=sum(rounded)
                results[expression]=(value,expression,"")
            except Exception as exc:results[expression]=(None,expression,str(exc))
        return results
    finally:
        if workbook is not None:workbook.Close(SaveChanges=False)
        if excel is not None:excel.Quit()
        pythoncom.CoUninitialize()


def read_saved_cells(path: str,sheet: str,addresses: list[str]):return read_saved_expressions(path,sheet,addresses,"volume")


def read_saved_cell(path: str,sheet: str,address: str,kind: str="volume"):
    expression=normalize_expression(address);result=read_saved_expressions(path,sheet,[expression],kind)[expression]
    if result[2]:raise ValueError(result[2])
    return result[0],result[1]


def _find_workbook(excel,path: str):
    full=str(Path(path).resolve()).casefold()
    return next((book for book in excel.Workbooks if str(book.FullName).casefold()==full),None)


def open_link_window(path: str,sheet: str="",address: str="",geometry: tuple[int,int,int,int] | None=None) -> dict:
    """기존 통합문서는 새 보기 창을 만들고, 프로그램이 연 파일은 소유권을 기록한다."""
    pythoncom,client=_excel_modules();pythoncom.CoInitialize();excel=None;previous_move_after_return=None
    try:
        excel=client.Dispatch("Excel.Application");previous_move_after_return=bool(excel.MoveAfterReturn);excel.MoveAfterReturn=False;workbook=_find_workbook(excel,path);opened=workbook is None
        if opened:workbook=excel.Workbooks.Open(str(Path(path).resolve()),UpdateLinks=0,ReadOnly=False);window=workbook.Windows(1)
        else:window=workbook.NewWindow()
        excel.Visible=True;window.Activate()
        if sheet:workbook.Worksheets(str(sheet)).Activate()
        if address:
            try:workbook.Worksheets(str(sheet)).Range(normalize_expression(address)).Select()
            except Exception:pass
        window.WindowState=-4143;hwnd=int(window.Hwnd);caption=str(window.Caption)
        if geometry and hwnd:
            x,y,width,height=geometry;ctypes.windll.user32.SetWindowPos(hwnd,0,int(x),int(y),int(width),int(height),0x0004|0x0010)
        return {"path":str(Path(path).resolve()),"caption":caption,"opened_workbook":opened,"hwnd":hwnd,"move_after_return":previous_move_after_return}
    except Exception:
        if excel is not None and previous_move_after_return is not None:
            try:excel.MoveAfterReturn=previous_move_after_return
            except Exception:pass
        raise
    finally:pythoncom.CoUninitialize()


def open_and_activate(path: str,sheet: str="") -> None:
    pythoncom,client=_excel_modules();pythoncom.CoInitialize()
    try:
        excel=client.Dispatch("Excel.Application");workbook=_find_workbook(excel,path)
        if workbook is None:workbook=excel.Workbooks.Open(str(Path(path).resolve()),UpdateLinks=0,ReadOnly=False)
        excel.Visible=True;workbook.Activate()
        if sheet:workbook.Worksheets(str(sheet)).Activate()
        excel.WindowState=-4143
    finally:pythoncom.CoUninitialize()


def close_link_window(token: dict | None) -> None:
    if not token:return
    pythoncom,client=_excel_modules();pythoncom.CoInitialize()
    closed=False
    try:
        excel=client.GetActiveObject("Excel.Application");excel.MoveAfterReturn=bool(token.get("move_after_return",True));workbook=_find_workbook(excel,token.get("path",""))
        if workbook is None:return
        if token.get("opened_workbook"):
            if bool(workbook.Saved):workbook.Close(SaveChanges=False);closed=True
        else:
            window=next((item for item in workbook.Windows if int(item.Hwnd)==int(token.get("hwnd",0))),None)
            if window is not None:window.Close();closed=True
    except Exception:pass
    finally:
        pythoncom.CoUninitialize()
        # Dispatch로 새 Excel을 만든 직후 ROT 등록이 늦어지는 PC에서도
        # 프로그램이 만든 정확한 보기 창만 닫히도록 HWND를 보조 경로로 사용한다.
        hwnd=int(token.get("hwnd",0) or 0)
        if not closed and hwnd and ctypes.windll.user32.IsWindow(hwnd):ctypes.windll.user32.PostMessageW(hwnd,0x0010,0,0)


def active_selection() -> tuple[str,str,str,bool]:
    pythoncom,client=_excel_modules();pythoncom.CoInitialize()
    try:
        excel=client.GetActiveObject("Excel.Application");workbook=excel.ActiveWorkbook;sheet=excel.ActiveSheet;target=excel.Selection
        if workbook is None or sheet is None or target is None:raise RuntimeError("Excel에서 셀을 선택해 주세요.")
        areas=[normalize_cell(str(area.Address)) for area in target.Areas]
        return str(workbook.FullName),str(sheet.Name),normalize_expression(",".join(areas)),bool(workbook.Saved)
    finally:pythoncom.CoUninitialize()
