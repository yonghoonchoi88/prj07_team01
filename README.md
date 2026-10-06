# 조각김치 이물검출 라벨링 프로그램 (v3.0)

조각김치 이미지에서 이물질 BBox 라벨을 검수하고 수정하는 팀 프로젝트입니다.
이 문서는 **팀 공통 규칙**을 모아 둔 곳입니다. 매일의 작업 기록은 `daily_log.csv`에 남깁니다.

---

## 0. 실행 방법

```bash
pip install -r requirements.txt     # pillow, pyyaml
python main.py
```

1. 왼쪽 위 **작업자 정보**에서 `작업자` 또는 `검수자`를 고르고, 이름을 고릅니다.
2. **파일 > 폴더 열기 (Ctrl+O)** 로 데이터 폴더(예: `이물검출_학습데이터1/`)를 선택합니다.
3. BBox를 수정하고 왼쪽 아래 **scene_type**을 고른 뒤 **저장 (Ctrl+S)** 합니다.

## 1. 데이터 및 보안 규칙

- 원본 데이터는 **훼손하지 않는다.** → 원본 라벨은 `labels/Raw`에 보관하고, 프로그램은 Raw에 **저장하지 않는다.**
- 데이터는 **외부로 유출하지 않는다.**

## 2. 데이터 구조

| 파일 | 내용 |
|---|---|
| JPG | 원본 사진 |
| TXT | 이물질의 Class와 BBox 좌표 (YOLO 형식: `class x_center y_center width height`, 0~1) |
| `labels/label.csv` | 모든 라벨 저장 기록 (파일명, 작업일자, work/final, 이름, scene_type) |

## 3. 폴더 구조 및 작업 흐름

```
RAW  ──(작업자 저장)──▶  WORK  ──(검수자 저장 + 검사 통과)──▶  FINAL
```

```
이물검출_학습데이터1/
├── images/
│   └── train/250424_153512_001.jpg
└── labels/
    ├── Raw/train/250424_153512_001.txt     ← 원본 (읽기 전용)
    ├── Work/train/250424_153512_001.txt    ← 작업 중
    ├── Final/train/250424_153512_001.txt   ← 검수 완료
    └── label.csv                           ← 작업 기록
```

| 단계 | 규칙 |
|---|---|
| RAW | 원본 보관용. **절대 수정하지 않는다.** 프로그램도 Raw에는 쓰지 않는다. |
| WORK | 라벨 작업 중인 파일. **작업자가 저장하면 WORK에만 저장된다.** 추가 수정이 필요한 파일은 FINAL로 넘기지 않는다. |
| FINAL | **검수자가 저장하면 FINAL에만 저장된다.** 저장 전에 Class·좌표·scene_type 검사를 하고, 에러가 있으면 저장하지 않는다. 저장되면 WORK에 있던 같은 파일은 정리된다(= WORK → FINAL 이동). |

- **이미지를 열 때 읽는 순서:** `WORK` → `FINAL` → `RAW` (작업 중인 파일이 가장 최신)
- **이미지 목록 표시:** ✔ FINAL / ✎ WORK / ○ RAW / · 라벨 없음
- **처음 폴더를 열 때:** 예전 위치(`labels/train/*.txt`)에 라벨이 있으면 `labels/Raw`로 **복사**할지 물어본다. (기존 파일은 그대로, Raw에 이미 있는 파일은 덮어쓰지 않음)
- **RAW 원본으로 되돌리기:** 파일 메뉴에서 Raw의 BBox를 다시 불러올 수 있다. 저장하면 역할에 맞는 폴더(작업자 WORK / 검수자 FINAL)에 반영된다.

## 4. 역할 (작업자 / 검수자)

- 왼쪽 위 **작업자 정보**에서 **작업자 / 검수자 중 하나만** 고른다. (라디오 버튼)
- 이름은 `configs/classes.yaml`의 `members` 목록에서 고른다: **최용훈, 박건, 이승훈, 김하민, 심준형**
- 역할과 이름을 고르지 않으면 저장할 수 없다.

| 역할 | 저장 위치 | 저장 버튼 | label.csv `work_type` |
|---|---|---|:---:|
| 작업자 | `labels/Work` **에만** | 초록 `저장 → WORK` | `work` |
| 검수자 | `labels/Final` **에만** | 보라 `검수 저장 → FINAL` | `final` |

## 5. scene_type (이미지 전체 정보)

`scene_type`은 **YOLO Class가 아니다.** BBox 하나하나가 아니라 **이미지 전체가 어떤 형태인지** 기록하는 보조 정보로, TXT에는 들어가지 않고 `label.csv`에만 기록된다.

| scene_type | 의미 |
|---|---|
| `kimchi_with_target` | 김치와 이물질 |
| `normal_kimchi` | 김치만 |
| `target_only` | 이물질만 |
| `other_review` | 바로 분류하기 어려운 이미지 |

- scene_type을 고르지 않으면 저장할 수 없다.
- scene_type을 바꾸는 것도 **변경 사항**으로 본다. (저장 안 됨 표시)
- 이미지를 다시 열면 `label.csv`의 **가장 마지막 기록**으로 scene_type이 표시된다.
- 검수자 저장 시 아래 경우는 한 번 더 확인한다: `normal_kimchi`인데 BBox가 있음 / `kimchi_with_target`·`target_only`인데 BBox가 0개 / `other_review`를 FINAL로 확정

## 6. 작업 기록 (`labels/label.csv`)

폴더를 열면 `labels/label.csv`가 없을 때 새로 만들어지고, **저장할 때마다 한 줄씩 추가**된다. (지우거나 고치지 않고 쌓는 작업 일지)

```csv
file_name,work_date,work_type,worker,scene_type
train/a.jpg,2026-10-06 14:23:05,work,최용훈,kimchi_with_target
train/a.jpg,2026-10-06 15:02:41,final,박건,kimchi_with_target
```

| 컬럼 | 내용 |
|---|---|
| `file_name` | 이미지 파일명 (images 폴더 기준 상대 경로) |
| `work_date` | 저장한 날짜·시각 |
| `work_type` | `work`(작업자) / `final`(검수자) |
| `worker` | 저장한 사람 이름 |
| `scene_type` | 이미지 전체 형태 |

- 엑셀에서 한글이 깨지지 않도록 `UTF-8 (BOM)`으로 저장한다.
- ⚠ **엑셀로 label.csv를 열어 둔 채 저장하면** 기록이 실패한다. (TXT는 저장됨, 경고 표시) → 엑셀을 닫고 다시 저장한다.

## 7. Class 기준 (0~6)

Class 목록은 **`configs/classes.yaml`** 에서 관리한다. (프로그램이 실제로 읽는 설정 파일)
`enabled: false`인 Class는 선택할 수 없고, 이 Class가 남아 있으면 FINAL로 넘어가지 않는다.

| Class ID | 이물 종류 | 사용 여부 |
|:---:|---|---|
| 0 | 나뭇잎·종이류 | 사용 |
| 1 | 플라스틱류·돌·금속류 | 사용 |
| 2 | 나뭇가지류 | 사용 |
| 3 | 벌레류 | 사용 |
| 4 | 고무장갑 | **사용하지 않음** (`enabled: false`) |
| 5 | 병해·갈변 | 사용 |
| 6 | 파·고추 | 사용 |

## 8. BBox 기준

- BBox는 **새로 치지 않고, 기존 박스를 수정**한다. → 프로그램은 **선택 이동 모드**로 시작한다.
- 박스는 이물질에 맞춰 **타이트하게** 친다.

## 9. 코드 구조

```
labeling_tool/
├── main.py                  # 프로그램 시작 (classes.yaml 읽기 → 화면 띄우기)
├── requirements.txt
├── src/
│   ├── ui/
│   │   ├── main_window.py   # 화면 구성, 버튼·메뉴·단축키 이벤트
│   │   └── canvas.py        # 이미지 표시, Zoom/Pan, 마우스 처리
│   ├── bbox/
│   │   ├── bbox_manager.py  # BBox 생성·수정·삭제·되돌리기 (데이터)
│   │   └── bbox_editor.py   # 마우스 드래그로 그리기·이동·크기 조절
│   ├── yolo/
│   │   ├── yolo_loader.py   # YOLO TXT Load, Raw/Work/Final 경로 계산
│   │   └── yolo_writer.py   # YOLO TXT Save (작업자 → Work / 검수자 → Final)
│   ├── validation/
│   │   └── validator.py     # 파일·Class·좌표·scene_type 검사
│   └── records/
│       └── label_csv.py     # labels/label.csv 작업 기록
├── configs/
│   └── classes.yaml         # Class · 작업자 이름(members) · scene_types 설정
└── README.md
```

| 폴더 | 역할 |
|---|---|
| `main.py` | 프로그램 시작 |
| `ui/` | 화면 구성과 버튼·이벤트 처리 |
| `bbox/` | BBox 생성·수정·삭제 |
| `yolo/` | YOLO TXT Load / Save (역할별 저장 위치) |
| `validation/` | 파일·Class·좌표·scene_type 검사 |
| `records/` | label.csv 작업 기록 |
| `configs/` | Class와 프로그램 설정 |

## 10. 프로그램 화면 구성

| 영역 | 구성 |
|---|---|
| 왼쪽 위 | 작업자 정보: 작업자/검수자 선택, 이름 선택, 저장 위치 안내 |
| 왼쪽 가운데 | 이미지 목록(✔✎○ 단계 표시), 폴더 열기, FINAL 진행률 / WORK·RAW 개수 |
| 왼쪽 아래 | scene_type 선택 (이미지 전체) |
| 가운데 | 단계 배지(RAW/WORK/FINAL/NEW) + 파일명, 이미지 캔버스 |
| 오른쪽 위 | Class 선택 (새 BBox의 Class / 선택한 BBox의 Class 변경), 사용 안 하는 Class는 회색 |
| 오른쪽 가운데 | 선택된 BBox 정보 (Class, X중심, Y중심, 너비, 높이), 적용(Enter) |
| 오른쪽 아래 | 현재 이미지의 BBox 목록 |
| 아래 | 보기 도구 (Zoom In/Out, Fit, Pan) · 라벨 도구 (새 BBox, 선택 이동, 삭제) · 이동/저장 (이전 A, 다음 D, **저장** (작업자 → WORK / 검수자 → FINAL), 저장 후 다음) |

**데이터 흐름:** 역할·이름 선택 → 폴더 선택 → 이미지·라벨 읽기 (WORK > FINAL > RAW) → BBox 수정 + scene_type 선택 → 저장 (작업자 WORK / 검수자 검사 후 FINAL) → label.csv 기록

**주요 단축키:** `A`/`D` 이전/다음 · `Ctrl+S` 저장 · `Ctrl+Enter` 저장 후 다음 · `W`/`E`/`H` 모드 · `0~6` Class · `Delete` 삭제 · `Ctrl+Z` 되돌리기 · `F5` 다시 불러오기

## 11. 버전 관리 규칙

| 변경 종류 | 규칙 | 예시 |
|---|---|---|
| 새 기능 추가 | 정수 자리 올림 | 1.0 → 2.0 |
| 버그 수정 | 소수점 자리 올림 | 1.0 → 1.1 |

## 12. 팀 운영

- **역할 분배:** 당일에 역할을 분배한다.
- **Must Have 범위:** 필수, 매우권장, 권장 항목을 모두 포함한다.

---

## 변경 이력

| 날짜 | 버전 | 내용 |
|---|:---:|---|
| 2026-10-02 | 1.0 | 최초 작성 (Day 01 기준 확정) |
| 2026-10-06 | 2.0 | 코드를 모듈 구조(`src/ui`, `bbox`, `yolo`, `validation`)로 분리 · `configs/classes.yaml` 도입 · 라벨 폴더를 `Raw / Work / Final`로 분리 · 완료(FINAL) 버튼과 검사 기능 추가 |
| 2026-10-06 | 3.0 | 작업자/검수자 역할 선택(5명) · 역할별 저장 위치 고정 (작업자 → Work, 검수자 → Final) · `scene_type` 추가 · `labels/label.csv` 작업 기록 · 완료 버튼은 검수자 저장으로 통합 |
