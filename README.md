# KHCM Traffic Analyzer

도로용량편람(2013)에 따른 도시 및 교외간선도로 분석용 Windows 데스크톱 프로그램입니다.

## 주요 기능

- 현황·사업 미시행·사업 시행·개선대책 시나리오별 구간 분석
- 평균통행속도 및 서비스수준(LOS) 산정
- Microsoft Excel 셀·범위의 교통량 합계와 PHF 연결, 주소식 직접 입력 및 일괄 경로 변경
- 분석 탭 메모, Ctrl+Z 되돌리기와 프로젝트에 저장되는 변경 기록
- 보고서용 표 및 부록용 세부 계산결과
- 교차로 연결 삽도와 입력표 간 양방향 구간 선택
- GitHub Releases 기반 자동 업데이트 확인·다운로드·무결성 검증·재설치

## 설치 및 실행

현재는 도시 및 교외간선도로 분석을 제공하며, 향후 교차로 분석 등 도로용량편람 기반 모듈을 같은 프로그램에 확장할 예정입니다.

일반 사용자는 [Releases](https://github.com/OutsiderStudent/khcm-traffic-analyzer/releases)에서 최신 EXE를 내려받아 실행합니다.

개발 실행:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .[dev]
.\.venv\Scripts\python.exe -m arterial_analysis
```

## 시험

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 배포

`v1.3.0`처럼 버전 태그를 GitHub에 푸시하면 Windows 실행파일을 빌드하고 GitHub Release에 첨부합니다. 프로그램은 시작 후 최신 Release를 비동기로 확인하며, 새 버전이 있을 때만 다운로드 페이지를 안내합니다.

## 주의

- Microsoft Excel 연동 기능은 Windows용 Microsoft Excel과 `pywin32`가 필요합니다.
- 분석 결과는 입력자료와 적용 조건에 따라 달라지므로 최종 성과품 작성 전 세부 계산결과를 검토해야 합니다.
- 도로용량편람 원문 및 사용자가 작성한 프로젝트·Excel 파일은 이 저장소에 포함하지 않습니다.
