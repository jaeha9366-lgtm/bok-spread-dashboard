# 위탁운용 분석 자료

이 폴더의 엑셀 원본은 Git에 올라가지 않습니다(`.gitignore`). 공개 저장소에는 보고서 비밀번호로 암호화한 파일만 `report_data_enc/` 에 저장됩니다.

## 방법 1 — 보고서 화면에서 업로드 (어느 PC에서나)

1. 대시보드 → 위탁운용 분석보고서 → 로그인 → **📤 자료 업로드**
2. 엑셀 파일 선택 + GitHub 토큰 입력 → **암호화 후 업로드**
3. GitHub Actions(`Update Report (uploaded data)`)가 보고서를 다시 만들어 게시합니다 (약 3~5분 + 사이트 반영 1~2분).

같은 종류의 자료는 교체되고, 올리지 않은 자료는 이전에 올린 것을 그대로 사용합니다.

**처음 한 번 설정**
- GitHub 저장소 → Settings → Secrets and variables → Actions → `REPORT_PASSWORD` 에 보고서 비밀번호 등록 (`BOK_API_KEY`는 기존 등록값 사용)
- 업로드용 토큰: GitHub → Settings → Developer settings → Fine-grained tokens → Repository access: 이 저장소만, Permissions: Contents **Read and write** (Actions Read 권한을 추가하면 진행 상황 조회가 더 안정적)

## 방법 2 — 이 PC에서 직접 생성

```
python dashboard_report.py            # 주간·월간 운용분석보고서 (report.html)
python dashboard_report_holdings.py   # 25년말 보유내역 분석 (report_holdings.html)
python report_inputs.py encrypt       # (선택) 현재 엑셀을 암호화해 report_data_enc/ 에 반영 → 커밋하면 Actions가 재생성
```

## 파일 종류 (파일명 키워드로 자동 인식)

| 키워드 | 내용 |
|---|---|
| `기준가` | 일자별 기준가 현황 (기준가·BM지수·듀레이션·YTM·순자산·좌수) |
| `매매` | 채권매매 손익률 (거래일·펀드·종목·만기·결제액·매매손익) |
| `헤지` | 해외채권형 환헤지비율 — 파일명 `26년 ○○ 헤지비율`의 ○○를 운용사명으로 사용 |
| `취합본` | 25년말 보유내역(집합투자증권명세) — 보유내역 분석 보고서용 |

비밀번호는 `.env` 의 `REPORT_PASSWORD` (GitHub에서는 Secrets)에서 읽습니다.
