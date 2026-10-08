# Subject 07 → Subject 08 Handoff

## 1. Handoff 목적

교과 7에서 검수 완료한 조각김치 이물검출 YOLO Dataset을
교과 8 Object Detection 학습에서 사용할 수 있도록 전달합니다.

<!-- AUTO:HANDOFF:START -->
## 2. FINAL Dataset

- 전체 이미지: 900장
- FINAL Image: 900장
- FINAL Label: 900개
- Label Format: YOLO Detection TXT
- 이미지와 TXT 파일명 Pair: 900쌍 일치

FINAL 데이터 위치 (Git 에 올리지 않음):

```
data/final/
├── images/
└── labels/
```

예:

```
250410_144403911987.jpg
250410_144403911987.txt
```

## 3. YOLO Label Format

TXT 한 줄은 객체 하나를 의미합니다.

```
class_id x_center y_center width height
```

좌표값은 이미지 크기 대비 0~1 범위의 정규화 좌표입니다.

## 4. Class 정보

- Class 0: 나뭇잎·종이류
- Class 1: 플라스틱류·돌·금속류
- Class 2: 나뭇가지류
- Class 3: 벌레류
- Class 4: 고무장갑 — 현재 사용하지 않음
- Class 5: 병해·갈변
- Class 6: 파·고추

- 상세 Class 기준: `docs/class_guide.md`
- 프로그램 Class 설정: `configs/classes.yaml`

## 5. BBox 기준

BBox는 객체 외곽에 최대한 밀착하여 작성했습니다. 상세 기준: `docs/bbox_guide.md`

## 6. QA 결과

- Validation PASS: 900장
- FAIL: 0장
- REVIEW: 0장
- Critical Error: 0건

상세 QA 결과: `reports/qa_summary.md` · 프로그램 테스트 결과: `reports/test_report.md`

## 7. Dataset 작업 이력

`manifests/dataset_manifest.csv` 에서 원본 출처 · 기존 Split · 작업자 · 작업 상태 · QA 상태 · REVIEW 사유를 확인합니다.

기존 Split 분포:

- dataset1 / train: 500장
- dataset2 / train: 220장
- dataset2 / validation: 180장
<!-- AUTO:HANDOFF:END -->


## 8. 데이터 구성과 교과 8 주의사항

### 8.1 데이터 구성 (scene_type · Class · 검수 결과)

**FINAL Class 별 BBox 수 (총 4,602개)**

| Class | 0 나뭇잎·종이 | 1 플라스틱·돌·금속 | 2 나뭇가지 | 3 벌레 | 4 고무장갑 | 5 병해·갈변 | 6 파·고추 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BBox | 868 | 1897 | 767 | 378 | 0 | 441 | 251 |

**scene_type 분포 (source_dataset / original_split 별)**

| source_dataset / original_split | kimchi_with_target | object_only | normal_kimchi | 합계 |
|---|---:|---:|---:|---:|
| dataset1 / train | 500 | 0 | 0 | 500 |
| dataset2 / train | 100 | 120 | 0 | 220 |
| dataset2 / validation | 150 | 30 | 0 | 180 |
| **합계** | **750** | **150** | **0** | **900** |

- 1차 검수 결과: DONE 431장 (기존 라벨 그대로) · EDITED 469장 (BBox 추가 +207 · 삭제 -4 · Class 변경 73장 · 좌표 조정 240장)
- Empty TXT: 0개 (900장 모두 BBox 1개 이상, 사람 검수로 확인)
- 교차검수: 900장 전부 1차 작업자와 다른 검수자가 QA PASS (본인 검수 0건)
- REVIEW 제기 27장 → 전부 해결 (too_small_to_identify 19 · class_ambiguous 7 · bbox_boundary_ambiguous 1)

### 8.2 교과 8에서 주의할 점

1. **정상 김치(Negative Sample) 0장**
   검출 대상이 없는 이미지가 없습니다. 이물이 없는 김치에서 잘못 검출하는 오탐(False Positive)은
   이 데이터만으로는 평가하기 어렵습니다. 필요하면 정상 이미지를 추가로 확보하는 것을 권장합니다.

2. **대상 객체 단독(object_only) 150장 (16.7%)**
   김치 배경이 없는 이미지로, 실제 생산 환경과 배경이 다릅니다. 모두 dataset2 에 있으며
   성능 평가 시 `kimchi_with_target` 과 분리해서 확인하는 것을 권장합니다.

3. **train / validation 간 유사 장면 가능성**
   파일명은 촬영 시각(`YYMMDD_HHMMSS…`)으로 보입니다. 기존 validation 180장 중 136장(76%)은
   60초 이내에 촬영된 train 이미지가 있습니다 (최소 8초 차이).
   같은 촬영 세션이 양쪽에 나뉘어 있어 평가 점수가 높게 나올 수 있으므로,
   교과 8에서 split 을 정할 때 **촬영 날짜·시간 구간 단위로 나누는 방식**을 검토해 주세요.

4. **Class 4(고무장갑)**: 900장 전체에서 발견 0건, `enabled: false` 유지.

5. **Class 불균형**: Class 1(1,897개)이 Class 6(251개)의 약 7.6배입니다. 학습 시 Class 별 Precision / Recall 을 따로 확인해 주세요.

> 교과 7은 기존 split 을 변경하지 않았습니다. 최종 Train / Validation / Test 구성은 교과 8에서 결정합니다.

## 9. 교과 8 전달 자료

```
handoff_subject08/
├── final_dataset/
│   ├── images/
│   └── labels/
├── dataset_manifest.csv
├── class_guide.md
├── bbox_guide.md
└── subject08_handoff.md
```

※ 실제 900장 데이터는 GitHub에 올리지 않고 내부 저장소 또는 지정된 교육환경에서 전달합니다.
(라벨링 프로그램 메뉴 **검사 → 교과 8 Handoff 패키지 만들기** 로 위 폴더를 만들 수 있습니다)

## 10. 교과 8에서 확인할 내용

1. 이미지와 TXT Pair가 정상인지 확인
2. Class 0~6 설정 확인
3. Class 4 사용 여부 확인
4. YOLO TXT 형식 확인
5. 기존 Dataset Split 정보 확인
6. 학습용 Dataset 설정 파일 구성
7. YOLO Object Detection 학습 진행
8. scene_type 별(kimchi_with_target / object_only)로 성능을 나눠서 평가
9. 촬영 시각 기준 유사 장면이 train / validation 에 섞이지 않았는지 확인 (8.2 참고)