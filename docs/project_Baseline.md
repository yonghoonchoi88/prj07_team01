# Team 1 Project Baseline

## 1. 공통 데이터 기준

- 전체 이미지: 900장
- Label Format: YOLO TXT
- Class: 0~6
- RAW 데이터 수정 금지

### 1.1. 데이터 구조

| 파일                 | 내용                                                                         |
| ------------------ | -------------------------------------------------------------------------- |
| JPG                | 원본 사진                                                                      |
| TXT                | 이물질의 Class와 BBox 좌표 (YOLO 형식: `class x_center y_center width height`, 0~1) |
| `labels/label.csv` | 모든 라벨 저장 기록 (파일명, 작업일자, work/final, 이름, scene_type)                        |

## 2. 우리 팀 작업 기준

- 왼쪽 위 **작업자 정보**에서 **작업자 / 검수자 중 하나만** 고른다. (라디오 버튼)
- 이름은 `configs/classes.yaml`의 `members` 목록에서 고른다
- 작업자 :  **최용훈, 박건, 이승훈, 김하민, 심준형**
- 역할과 이름을 고르지 않으면 저장할 수 없다.
- **검수자는 WORK에 파일이 있는 이미지만 저장할 수 있다.** 아래 이미지는 FINAL로 보낼 수 없고, 작업자가 먼저 WORK에 저장해야 한다.
    - RAW(원본)만 있는 이미지
    - 라벨이 없는 이미지
    - 이미 FINAL에 있는 이미지 (다시 고치려면 작업자가 WORK에 저장 → 검수자 재검수)
- 검수자는 `RAW 원본으로 되돌리기`를 쓸 수 없다. (RAW 내용이 WORK를 건너뛰고 FINAL로 가는 것을 막기 위해)

|역할|저장 위치|저장 버튼|label.csv `work_type`|
|---|---|---|:-:|
|작업자|`labels/Work` **에만**|초록 `저장 → WORK`|`work`|
|검수자|`labels/Final` **에만**|보라 `검수 저장 → FINAL`|`final`|


## 3. Git 기준

- 커밋 시 개인 branch에 커밋 후 push -> pull request 작성 -> merge
- **main** branch 에 올리지 않도록 주의한다.

```text
기능 하나 구현
→ 직접 실행
→ 정상 동작 확인
→ Commit
→ 다음 기능 개발

예:
feat: 이미지 불러오기 기능 구현
feat: BBox 추가 기능 구현
feat: YOLO TXT 저장 기능 구현
fix: BBox 저장 위치 오류 수정
```

## 4. secene_type (이미지 전체 정보)

`scene_type`은 **YOLO Class가 아니다.** BBox 하나하나가 아니라 **이미지 전체가 어떤 형태인지** 기록하는 보조 정보로, TXT에는 들어가지 않고 `label.csv`에만 기록된다.

|scene_type|의미|
|---|---|
|`kimchi_with_target`|김치와 이물질|
|`normal_kimchi`|김치만|
|`target_only`|이물질만|
|`other_review`|바로 분류하기 어려운 이미지|

- scene_type을 고르지 않으면 저장할 수 없다.
- scene_type을 바꾸는 것도 **변경 사항**으로 본다. (저장 안 됨 표시)
- 이미지를 다시 열면 `label.csv`의 **가장 마지막 기록**으로 scene_type이 표시된다.
- 검수자 저장 시 아래 경우는 한 번 더 확인한다: `normal_kimchi`인데 BBox가 있음 / `kimchi_with_target`·`target_only`인데 BBox가 0개 / `other_review`를 FINAL로 확정

## 5. 버전 관리 규칙

|변경 종류|규칙|예시|
|---|---|---|
|새 기능 추가|정수 자리 올림|1.0 → 2.0|
|버그 수정|소수점 자리 올림|1.0 → 1.1|
## 6. 팀 운영

- **역할 분배:** 당일에 역할을 분배한다.
- **Must Have 범위:** 필수, 매우권장, 권장 항목을 모두 포함한다.

## 7. 완료 기준

- 미처리 REVIEW: 0건
- Validation 오류: 0건
- 이미지와 TXT Pair 확인 완료
- 900장 전체 검수 완료
- FINAL 데이터 정리 완료