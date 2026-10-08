# Labeling Tool Test Report

기능 검증은 `기능 확인 → 1장 End-to-End → Golden Sample → Pilot Test → 전체 Validation → Acceptance Test`
순서로 확대합니다. 숫자 영역은 프로그램이 자동으로 갱신하고, FAIL 기록은 팀이 직접 적습니다.

<!-- AUTO:GOLDEN:START -->
## 1. Golden Test

### 테스트 목적
900장 전체 작업을 시작하기 전에 핵심 기능이 정상적으로 동작하는지 소수의 실제 데이터로 먼저 확인합니다.

### 테스트 데이터
- 실제 조각김치 이미지: 20장 (데이터셋 · split 이 고루 섞이도록 간격을 두고 선택)
- 실제 YOLO TXT: 대응하는 20개 (원본은 바꾸지 않고 임시 폴더에서 저장 · Reload)
- 실행 시각: 2026-10-07 14:49:18 · 소요 1.0초

### 테스트 결과

| 테스트 항목 | 결과 |
|---|---|
| 이미지 열기 | PASS (20/20) |
| 기존 YOLO TXT Load | PASS (20/20) |
| 기존 BBox 표시 (좌표 변환) | PASS (20/20) |
| BBox 추가 | PASS (20/20) |
| BBox 수정 | PASS (20/20) |
| BBox 삭제 | PASS (20/20) |
| Class 변경 | PASS (20/20) |
| Zoom | PASS (20/20) |
| Pan | PASS (20/20) |
| YOLO TXT 저장 | PASS (20/20) |
| 저장 후 Reload | PASS (20/20) |
| Validation | PASS (20/20) |

최종 결과: 20 / 20 PASS

### 실패 항목
- 없음
<!-- AUTO:GOLDEN:END -->

---

<!-- AUTO:PILOT:START -->
## 2. Pilot Test

### 테스트 목적
실제 900장 작업을 시작하기 전에 더 많은 데이터에서 프로그램이 안정적으로 동작하는지 확인합니다.

### 테스트 데이터
- 실제 조각김치 이미지: 50장 (데이터셋 · split 이 고루 섞이도록 간격을 두고 선택)
- 실제 YOLO TXT: 대응하는 50개 (원본은 바꾸지 않고 임시 폴더에서 저장 · Reload)
- 실행 시각: 2026-10-07 14:49:21 · 소요 2.6초

### 테스트 결과

| 테스트 항목 | 결과 |
|---|---|
| 이미지 열기 | PASS (50/50) |
| 기존 YOLO TXT Load | PASS (50/50) |
| 기존 BBox 표시 (좌표 변환) | PASS (50/50) |
| BBox 추가 | PASS (50/50) |
| BBox 수정 | PASS (50/50) |
| BBox 삭제 | PASS (50/50) |
| Class 변경 | PASS (50/50) |
| Zoom | PASS (50/50) |
| Pan | PASS (50/50) |
| YOLO TXT 저장 | PASS (50/50) |
| 저장 후 Reload | PASS (50/50) |
| Validation | PASS (50/50) |

최종 결과: 50 / 50 PASS

### 실패 항목
- 없음
<!-- AUTO:PILOT:END -->

### Pilot 중 발견된 문제 (직접 작성)

> 처음부터 전부 PASS 일 필요는 없습니다. **문제 → 원인 → 조치 → 재시험** 을 남기는 것이 중요합니다.

#### FAIL-01 (개발 중 실제로 발견 · v2.1 에서 수정)
- 문제: 검수자가 RAW 원본만 있는 이미지를 1차 검수 없이 바로 FINAL 로 저장할 수 있었음
- 원인: FINAL 저장 시 work(1차 검수 결과)가 있는지 확인하지 않음
- 조치: 화면과 저장 함수 두 곳에서 work 존재 여부 확인 (이중 안전장치)
- 재시험: PASS

#### FAIL-02 (10-08 발견 · 수정)
- 문제: FINAL 증빙 문서의 이미지 10개가 GitHub 에서 표시되지 않음
- 원인: 이미지 경로에 `FINAL_YOLO_images/` 폴더명이 빠짐
- 조치: 모든 이미지 경로에 폴더명 추가 (b0ddb7f)
- 재시험: 10개 링크 모두 파일 존재 확인 PASS

---

<!-- AUTO:ACCEPTANCE:START -->
## 3. Final Acceptance Test

### 테스트 목적
900장 전체 검수 작업이 끝난 뒤 프로그램과 FINAL 데이터가 최종 사용 가능한 상태인지 확인합니다.

### 확인 항목

| 확인 항목 | 결과 |
|---|---|
| 900장 이미지 탐색 가능 | PASS |
| 이미지와 TXT Pair 정상 (FINAL) | PASS |
| 저장 후 Reload 정상 (Golden · Pilot) | PASS |
| 미처리 REVIEW 없음 | PASS |
| Critical Error 없음 | PASS |
| Validation 오류 없음 | PASS |
| 900장 전체 QA PASS | PASS |

### 최종 결과

- 전체 대상: 900장
- Critical Error: 0건
- Unresolved Review: 0건
- Validation Error: 0건

최종 판정: **ACCEPTED**
<!-- AUTO:ACCEPTANCE:END -->

---

## 4. Final Acceptance Test (README 기반 사용자 시험)
- 시험자: 이승훈 (개발 미참여) · 일시: 2026-10-07 · 기준: README.md 만 참고

| 항목 | 결과 | 비고 |
|---|---|---|
| 프로그램 실행 (python main.py) | PASS | |
| 이미지 폴더 열기 | PASS | |
| 기존 YOLO TXT Load · BBox 표시 | PASS | |
| BBox 추가 / 수정 / 삭제 | PASS | |
| Class 변경 | PASS | |
| Zoom / Pan | PASS | | 
| Save → Reload | PASS | |
| Validation (F7) | PASS | |
| RAW 원본 보존 확인 | PASS | |

최종 판정: ACCEPTED
