# Subject 07 → Subject 08 Handoff

## 1. Handoff 목적

교과 7에서 검수 완료한 조각김치 이물검출 YOLO Dataset을
교과 8 Object Detection 학습에서 사용할 수 있도록 전달합니다.

<!-- AUTO:HANDOFF:START -->
## 2. FINAL Dataset

- 전체 이미지: 900장
- FINAL Image: 0장
- FINAL Label: 0개
- Label Format: YOLO Detection TXT
- 이미지와 TXT 파일명 Pair: 0쌍 일치

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

- Validation PASS: 0장
- FAIL: 0장
- REVIEW: 23장
- Critical Error: 0건

상세 QA 결과: `reports/qa_summary.md` · 프로그램 테스트 결과: `reports/test_report.md`

## 7. Dataset 작업 이력

`manifests/dataset_manifest.csv` 에서 원본 출처 · 기존 Split · 작업자 · 작업 상태 · QA 상태 · REVIEW 사유를 확인합니다.

기존 Split 분포:

- dataset1 / train: 500장
- dataset2 / train: 220장
- dataset2 / validation: 180장
<!-- AUTO:HANDOFF:END -->

## 8. 교과 8 전달 자료

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

## 9. 교과 8에서 확인할 내용

1. 이미지와 TXT Pair가 정상인지 확인
2. Class 0~6 설정 확인
3. Class 4 사용 여부 확인
4. YOLO TXT 형식 확인
5. 기존 Dataset Split 정보 확인
6. 학습용 Dataset 설정 파일 구성
7. YOLO Object Detection 학습 진행
