# QA Summary

조각김치 이물검출 라벨 900장의 품질검사 결과입니다.
아래 숫자는 라벨링 프로그램의 **검사 → 산출물 생성** 으로 자동 갱신됩니다.

<!-- AUTO:DATA:START -->
## 1. 전체 데이터

- 전체 이미지: 900장
- FINAL 이미지: 900장 / FINAL TXT: 900개 (이미지-TXT Pair 일치 900쌍)
- 1차 검수 완료: 900장 / 900장 (DONE 431 · EDITED 469 · REVIEW 0)
- 라벨 검수 완료 (QA PASS): 900장 / 900장 (100.0%)

| source_dataset | original_split | 이미지 수 |
|---|---|---:|
| dataset1 | train | 500 |
| dataset2 | train | 220 |
| dataset2 | validation | 180 |
<!-- AUTO:DATA:END -->

---

<!-- AUTO:VALIDATION:START -->
## 2. 자동 Validation 결과

Validation 실행 횟수: 10회 (manifests/validation_runs.csv)

### 최초 실행
- 실행 시각: 2026-10-07 11:28:30
- PASS: 900장
- FAIL: 0건

### 최종 실행
- 실행 시각: 2026-10-07 16:16:25
- PASS: 900장
- FAIL: 0건

### 발견된 오류 (이미지 수 기준)

| 오류 종류 | 최초 실행 | 최종 실행 |
|---|---:|---:|
| 이미지-TXT Pair 오류 | 0 | 0 |
| 좌표 형식 오류 | 0 | 0 |
| Class ID 오류 | 0 | 0 |
| 사용하지 않는 Class(4) | 0 | 0 |
| BBox 이미지 경계 초과 | 0 | 0 |
| Empty TXT 확인 필요 | 0 | 0 |
| scene_type 불일치 | 0 | 0 |
| Manifest 상태 오류 | 0 | 0 |

최초 실행 총 오류: 0건  →  최종 실행 총 오류: 0건

상세 목록: `reports/validation_report.csv`
<!-- AUTO:VALIDATION:END -->

---

<!-- AUTO:HUMAN:START -->
## 3. Human QA 결과

자동 Validation 에서 발견된 이미지와, 작업 중 REVIEW 로 올라온 이미지를 사람이 다시 확인했습니다.

- 검토 대상: 27건 (최초 Validation FAIL + REVIEW 제기)
- 수정 완료: 27건
- 미해결: 0건
- 교차검수 반려 (검수자 → REVIEW): 3건

### 1차 검수 상태 (현재)

| status | 의미 | 이미지 수 |
|---|---|---:|
| DONE | 기존 라벨이 맞아서 수정 없이 검수 완료 | 431 |
| EDITED | 기존 라벨을 수정 · 추가 · 삭제한 뒤 저장 | 469 |
| REVIEW | 판단이 어려워 추가 검수 필요 | 0 |
| (미작업) | 아직 1차 검수 전 | 0 |

### REVIEW 사유

| review_reason | 의미 | 제기된 이미지 | 현재 미해결 |
|---|---|---:|---:|
| `class_ambiguous` | Class 판단이 애매함 | 10 | 0 |
| `bbox_boundary_ambiguous` | BBox 경계가 애매함 | 1 | 0 |
| `object_separation_ambiguous` | 겹친 객체를 나누기 애매함 | 0 | 0 |
| `too_small_to_identify` | 너무 작아서 식별이 어려움 | 29 | 0 |
| `occlusion_ambiguous` | 가려져서 판단이 어려움 | 0 | 0 |
| `unused_class_found` | 사용하지 않는 Class(4 고무장갑) 발견 - 임의 삭제 금지 | 0 | 0 |
<!-- AUTO:HUMAN:END -->

---

<!-- AUTO:FINAL:START -->
## 4. 최종 결과

- PASS: 900장
- FAIL: 0장
- REVIEW: 0장

최종 판정: **QA 완료**

_자동 생성: 2026-10-07 16:16 · 데이터: `/home/user1/exe_01/master_data`_
<!-- AUTO:FINAL:END -->

---

## 5. 추가 통계 (수기 작성 · 2026-10-08)

### 5.1 scene_type 별 이미지 수

| scene_type | 의미 | 이미지 수 |
|---|---|---:|
| `kimchi_with_target` | 김치 + 검출 대상 객체 | 750 |
| `object_only` | 대상 객체 단독 | 150 |
| `normal_kimchi` | 정상 김치 | 0 |
| `other_review` | 분류 어려움 | 0 |

### 5.2 Empty TXT 확인 결과

- Empty TXT: **0개** — 900장 모두 BBox 1개 이상이며, 1차 검수와 교차검수에서 사람이 확인했습니다.
- 따라서 정상 김치(Negative) 이미지는 이 데이터셋에 포함되어 있지 않습니다. (교과 8 Handoff 8.2 참고)

### 5.3 Cross Review (교차검수) 결과

- 교차검수 대상: **900장 전수** (가이드의 DONE 표본검수 대신 전체를 교차검수)
- 본인이 1차 검수한 이미지를 본인이 PASS 한 건수: **0건** (`allow_self_review: false`)
- 검수자별 QA PASS: 박건 594 · 심준형 123 · 이승훈 100 · 최용훈 83
- 교차검수 반려: 3장 (4회) → 수정 후 모두 QA PASS
- REVIEW 제기: **27장** (too_small_to_identify 19 · class_ambiguous 7 · bbox_boundary_ambiguous 1) → 모두 해결

> 3장 'REVIEW 사유' 표의 '제기된 이미지' 값(10/1/29)은 이력 줄 수 기준으로 집계된 값이며,
> 실제 이미지 수는 위의 7/1/19 (합계 27장) 입니다.

### 5.4 RAW 최초 점검 (원본 상태, tools/label_stats.py)

| 항목 | 값 |
|---|---:|
| RAW 이미지 / TXT | 900 / 900 |
| 이미지-TXT Pair 일치 | 900 |
| Pair 누락 (TXT 없음 / 이미지 없음) | 0 / 0 |
| Empty TXT | 0 |
| Class 4 포함 TXT | 0 |

→ 원본 단계에서 형식 오류는 없었고, 품질 문제는 **라벨 의미(누락 · Class 오분류 · 좌표)** 에 있었습니다.
→ 2장의 Validation(F7) '최초 실행'은 작업 시작 후(10-07 11:28)에 기록되었으므로, **원본 상태 점검은 이 표를 기준**으로 봅니다.

### 5.5 Class 별 BBox 수 (RAW → FINAL)

| Class | 이름 | RAW | FINAL | 증감 |
|:-:|---|---:|---:|---:|
| 0 | 나뭇잎·종이류 | 716 | 868 | +152 |
| 1 | 플라스틱류·돌·금속류 | 1831 | 1897 | +66 |
| 2 | 나뭇가지류 | 911 | 767 | -144 |
| 3 | 벌레류 | 379 | 378 | -1 |
| 4 | 고무장갑 (미사용) | 0 | 0 | 0 |
| 5 | 병해·갈변 | 313 | 441 | +128 |
| 6 | 파·고추 | 249 | 251 | +2 |
| | **합계** | **4399** | **4602** | **+203** |

### 5.6 라벨 변경 내역

| 구분 | 이미지 수 | BBox |
|---|---:|---:|
| 변경 없음 (DONE) | 431 | - |
| 좌표만 조정 (EDITED) | 240 | - |
| BBox 추가 (EDITED) | 152 | +207 |
| BBox 삭제 (EDITED) | 4 | -4 |
| Class 변경 (EDITED, 개수 동일) | 73 | - |
| **합계** | **900** | **+203** |

- 검산: 개수·Class 변경 229장 + 좌표 조정 240장 = EDITED 469장, 나머지 431장 = DONE 으로 manifest 와 일치합니다.
- 주요 보정: 누락 BBox 추가(+207)가 가장 많았고, 나뭇가지류(-144)가 줄고 나뭇잎·종이류(+152) · 병해·갈변(+128)이 늘어
  **Class 재분류**가 함께 이루어졌습니다.