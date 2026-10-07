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

## 5. 메모 (직접 작성)

- 예) Empty TXT 4건은 이미지 확인 결과 정상 김치 → scene_type normal_kimchi 로 수정 후 PASS
