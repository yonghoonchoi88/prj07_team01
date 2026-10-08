# Team 1 Project Baseline (v4.1)

## 1. 공통 데이터 기준

- 전체 이미지: 900장 (기존 데이터셋 여러 개 · train / validation)
- Label Format: YOLO TXT (`class x_center y_center width height`, 0~1)
- Class: 0~6 (4 고무장갑은 사용하지 않음)
- **RAW 데이터 수정 금지** — 프로그램도 `data/raw` 에는 저장하지 않는다.
- 900장 JPG · TXT 와 FINAL 데이터는 **Git 에 올리지 않는다.**
- v4.0 부터 기존 작업 데이터는 쓰지 않고 **원본에서 새로 시작**한다.

### 1.1. 데이터 위치

| 위치 | 내용 | 누가 쓰나 |
|---|---|---|
| `data/raw/` | 원본 데이터셋 (JPG + TXT) | 아무도 안 씀 (읽기 전용) |
| `data/work/labels/` | 1차 검수 결과 TXT | 작업자 저장 · 검수자 반려 |
| `data/final/images/` · `data/final/labels/` | **QA PASS 데이터만** (이미지 + TXT 한 쌍) | 검수자 QA PASS |
| `data/manifests/dataset_manifest.csv` | 이미지 1장 = 1줄 작업대장 | 프로그램 자동 |
| `data/manifests/label_history.csv` | 작업 이력 (누가 · 언제 · 무엇을) | 프로그램 자동 |
| `data/manifests/validation_runs.csv` | 전체 Validation 실행 기록 | 프로그램 자동 |

## 2. 우리 팀 작업 기준

- 왼쪽 위 **작업자 정보**에서 **작업자(1차 검수) / 검수자(교차검수) 중 하나만** 고른다.
- 이름은 `configs/classes.yaml` 의 `members` 에서 고른다: **최용훈, 박건, 이승훈, 김하민, 심준형**
- 역할 · 이름 · scene_type 을 고르지 않으면 저장할 수 없다.

| 역할 | 저장 버튼 | 결과 | status | qa_status |
|---|---|---|---|---|
| 작업자 | 초록 `저장 → WORK` | `data/work` | DONE / EDITED (자동) · REVIEW (체크) | WAIT |
| 검수자 | 보라 `QA PASS → FINAL` | `data/final` (이미지 + TXT) | 그대로 | **PASS** |
| 검수자 | 주황 `반려 → REVIEW` | `data/work` | REVIEW (+사유) | WAIT |

- **status 자동 판정:** 원본 라벨과 같으면 `DONE`, 하나라도 다르면(수정 · 추가 · 삭제 · Class 변경) `EDITED`
- **REVIEW 는 사유(review_reason) 필수.** 6가지 중 하나를 고른다.
- **교차검수:** 본인이 1차 검수한 이미지는 본인이 QA PASS 할 수 없다.
- **raw → final 직행 금지:** 1차 검수(work)를 거친 이미지만 QA PASS 할 수 있다.
- **QA PASS 전 자동 검사:** Class · 좌표 · 경계 · scene_type 오류가 있으면 FINAL 로 보내지 않는다.
- QA PASS 된 이미지를 다시 저장 · 반려하면 **final 에서 빠지고 WAIT** 로 돌아간다. (final = PASS 만)
- Class 4 가 보이면 **지우지 말고** REVIEW (`unused_class_found`) 로 저장한다.

### 2.1. 실제 역할 분담

| 역할 | 담당 (이미지 수) |
|---|---|
| 1차 검수 (작업자) | 김하민 250 · 심준형 250 · 최용훈 150 · 박건 150 · 이승훈 100 |
| 교차검수 (검수자) | 박건 594 · 심준형 123 · 이승훈 100 · 최용훈 83 (본인 검수 0건) |
| REVIEW 최종 판단 | 팀 회의 (팀장 최용훈 + 해당 검수자) — 27장 |

## 3. scene_type (이미지 전체 정보)

`scene_type` 은 **YOLO Class 가 아니다.** 이미지 전체가 어떤 형태인지 기록하는 보조 정보로, TXT 에는 들어가지 않고 manifest 에만 기록된다.

| scene_type | 의미 |
|---|---|
| `kimchi_with_target` | 김치 + 검출 대상 객체 |
| `normal_kimchi` | 정상 김치 (검출 대상 없음 → 빈 TXT 허용) |
| `object_only` | 대상 객체만 단독으로 있는 이미지 |
| `other_review` | 바로 분류하기 어려운 이미지 |

## 4. review_reason

| review_reason | 의미 |
|---|---|
| `class_ambiguous` | Class 판단이 애매함 |
| `bbox_boundary_ambiguous` | BBox 경계가 애매함 |
| `object_separation_ambiguous` | 겹친 객체를 나누기 애매함 |
| `too_small_to_identify` | 너무 작아서 식별이 어려움 |
| `occlusion_ambiguous` | 가려져서 판단이 어려움 |
| `unused_class_found` | 사용하지 않는 Class(4 고무장갑) 발견 |

## 5. 작업 순서 (교과 7 기준)

1. 기능 확인 → 1장 End-to-End → **Golden Test (20장)** → **Pilot Test (50장)**
2. 900장 작업 분배 → 1차 검수 (작업자) → 교차검수 (검수자)
3. 전체 Validation (F7) → 실패 수정 → 다시 검사
4. 미해결 REVIEW 팀 회의로 결정 → QA PASS
5. 산출물 생성 → `manifests/` · `reports/` · `docs/subject08_handoff.md` 커밋
6. 교과 8 Handoff 패키지 전달

## 6. Git 기준

- 개인 branch 에 커밋 → push → Pull Request → merge. **main 에 직접 올리지 않는다.**

```text
기능 하나 구현 → 직접 실행 → 정상 동작 확인 → Commit → 다음 기능

feat: 새 기능 / fix: 버그 수정 / docs: 문서 / chore: 기타
```

## 7. 버전 관리 규칙

| 변경 종류 | 규칙 | 예시 |
|---|---|---|
| 새 기능 추가 | 정수 자리 올림 | 3.0 → 4.0 |
| 버그 수정 | 소수점 자리 올림 | 4.0 → 4.1 |

## 8. 팀 운영

- **역할 분배:** 당일에 역할을 분배한다. (작업 범위는 겹치지 않게)
- **결과 공유:** 하루 작업 후 `파일 > 내 결과 묶음 만들기` → 팀장이 합치기 → 합친 결과를 다시 공유
- **Must Have 범위:** 필수, 매우권장, 권장 항목을 모두 포함한다.

## 9. 완료 기준

- 900장 전체 QA PASS (`qa_status = PASS`)
- 미처리 REVIEW: 0건
- Validation 오류: 0건 (최종 실행)
- `data/final/images` 와 `data/final/labels` Pair 900쌍 일치
- QA Summary · Test Report · Handoff 문서 작성 완료
