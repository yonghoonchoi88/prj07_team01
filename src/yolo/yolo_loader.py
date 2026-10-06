"""
yolo_loader.py - 작업 폴더 구성 + YOLO TXT 불러오기 (Load)
=========================================================

[담당]
    - 선택한 폴더(예: data) 아래의 '모든' 이미지를 찾아 하나의 작업 목록으로 묶기
    - 이미지마다 출처(source_dataset)와 원래 위치(original_split) 기록
    - 통합 RAW / WORK / FINAL 라벨 경로 계산
    - 지금 어떤 단계의 라벨을 읽어야 하는지 결정 (WORK > FINAL > RAW)
    - YOLO TXT → BBox 목록 (원본 픽셀 좌표)

[폴더 구조] data 하나만 열면 됩니다.
    data/                                   ← 이 폴더를 엽니다
    ├─ 이물검출_학습데이터1/
    │   ├─ images/train/a.jpg
    │   └─ labels/train/a.txt               ← 원래 라벨 (읽기만, 처음 한 번 Raw 로 복사)
    ├─ 이물검출_학습데이터2/
    │   ├─ images/train/b.jpg
    │   ├─ images/validation/c.jpg
    │   └─ labels/...
    └─ labels/                              ← 통합 작업 폴더 (프로그램이 만듦)
        ├─ Raw/a.txt  b.txt  c.txt          ← 원본 보존 (저장 금지)
        ├─ Work/                            ← 작업자 저장
        ├─ Final/                           ← 검수 완료
        └─ label.csv                        ← 통합 작업 기록 (source_dataset · original_split · qa_status 포함)

    이물검출_학습데이터1 처럼 데이터셋 폴더 하나만 열어도 똑같이 동작합니다.
    (그때는 그 폴더 안의 labels/Raw · Work · Final 이 통합 폴더가 됩니다)

이 파일은 '읽기'만 합니다. 디스크에 쓰는 일은 yolo_writer.py 담당입니다.
"""

import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# ---------- 라벨 단계(폴더 이름) ----------
STAGE_RAW = "Raw"
STAGE_WORK = "Work"
STAGE_FINAL = "Final"
STAGES = (STAGE_RAW, STAGE_WORK, STAGE_FINAL)

# 화면을 열 때 어떤 라벨을 보여줄지 우선순위
#   WORK  : 작업하던 게 있으면 그게 가장 최신
#   FINAL : 이미 검수가 끝난 이미지
#   RAW   : 아직 아무도 손대지 않은 원본
LOAD_PRIORITY = (STAGE_WORK, STAGE_FINAL, STAGE_RAW)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")
LABELS_DIRNAME = "labels"


# ==================================================
# 1. 좌표 변환 (YOLO → 픽셀)
# ==================================================

def yolo_to_bbox(x_center, y_center, width, height, img_w, img_h):
    """YOLO 좌표(0~1) → 픽셀 좌표 (x1, y1, x2, y2)"""
    x1 = (x_center - width / 2) * img_w
    y1 = (y_center - height / 2) * img_h
    x2 = (x_center + width / 2) * img_w
    y2 = (y_center + height / 2) * img_h
    return x1, y1, x2, y2


# ==================================================
# 2. 이미지 한 장의 정보
# ==================================================

@dataclass
class ImageItem:
    """
    이미지 한 장 = 실제 파일 위치 + 통합 폴더에서 쓰는 이름 + 출처 정보

        path            : 실제 이미지 파일   (data/이물검출_학습데이터2/images/train/b.jpg)
        key             : 통합 이름          (b.jpg)  ← Raw/Work/Final 의 TXT 이름, label.csv 의 file_name
        source_dataset  : 어느 데이터셋에서 왔는지 (dataset2)
        original_split  : 기존 train/validation 위치 (train)
        dataset_dir     : 데이터셋 폴더      (data/이물검출_학습데이터2)
        labels_dir      : 통합 labels 폴더   (data/labels)
    """
    path: Path
    key: str
    source_dataset: str
    original_split: str
    dataset_dir: Path
    labels_dir: Path

    @property
    def label_name(self):
        return Path(self.key).stem + ".txt"

    def label_path(self, stage):
        """통합 단계 폴더의 라벨 경로.  예) data/labels/Work/b.txt"""
        if stage not in STAGES:
            raise ValueError(f"알 수 없는 단계: {stage}")
        return self.labels_dir / stage / self.label_name

    def original_label_path(self):
        """데이터셋에 원래 들어 있던 라벨.  예) data/이물검출_학습데이터2/labels/train/b.txt"""
        return self.dataset_dir / LABELS_DIRNAME / self.original_split / (self.path.stem + ".txt")

    def legacy_stage_path(self, stage):
        """v2.x 때 데이터셋마다 따로 만들던 단계 폴더.  예) .../labels/Work/train/b.txt"""
        return self.dataset_dir / LABELS_DIRNAME / stage / self.original_split / (self.path.stem + ".txt")

    @property
    def origin_text(self):
        """화면 표시용.  예) dataset2 · train"""
        return " · ".join(t for t in (self.source_dataset, self.original_split) if t)


class Workspace:
    """선택한 폴더 하나 = 작업 공간 하나 (이미지 목록 + 통합 labels 폴더)"""

    def __init__(self, root, items, renamed):
        self.root = Path(root)
        self.labels_dir = self.root / LABELS_DIRNAME
        self.items = items
        self.renamed = renamed          # 파일명이 겹쳐서 이름 앞에 출처를 붙인 이미지 수

    @property
    def csv_path(self):
        return self.labels_dir / "label.csv"

    @property
    def datasets(self):
        return sorted({it.source_dataset for it in self.items})


# ==================================================
# 3. 폴더 → 작업 공간 만들기
# ==================================================

def dataset_label(folder_name):
    """'이물검출_학습데이터2' → 'dataset2'  (끝에 숫자가 없으면 폴더 이름 그대로)"""
    m = re.search(r"(\d+)\s*$", folder_name)
    return f"dataset{int(m.group(1))}" if m else folder_name


def build_workspace(folder):
    """
    선택한 폴더 아래(하위 폴더 전부)의 이미지를 모아 작업 공간을 만듭니다.
    labels 폴더 안은 이미지로 보지 않습니다.
    """
    root = Path(folder)
    labels_dir = root / LABELS_DIRNAME
    found = []
    for p in sorted(root.rglob("*")):
        if not (p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS):
            continue
        rel = p.relative_to(root).parts
        if LABELS_DIRNAME in rel[:-1]:
            continue

        if "images" in rel[:-1]:
            # .../<데이터셋>/images/<split>/a.jpg
            idx = len(rel) - 2 - rel[:-1][::-1].index("images")
            ds_parts, split_parts = rel[:idx], rel[idx + 1:-1]
        else:
            # images 폴더가 없으면 이미지가 있는 폴더 자체를 데이터셋으로 봅니다. (Day 1 방식)
            ds_parts, split_parts = rel[:-1], ()
        dataset_dir = root.joinpath(*ds_parts) if ds_parts else root
        source = dataset_label(ds_parts[-1] if ds_parts else root.name)
        found.append((p, source, "/".join(split_parts), dataset_dir))

    # 통합 폴더에 모이면 파일명이 겹칠 수 있으니 확인 → 겹치는 것만 앞에 출처를 붙입니다.
    stem_count = Counter(p.stem for p, *_ in found)
    items, used, renamed = [], set(), 0
    for p, source, split, dataset_dir in found:
        key = p.name
        if stem_count[p.stem] > 1:
            prefix = "_".join(t for t in (source, split.replace("/", "_")) if t)
            key = f"{prefix}__{p.name}"
            renamed += 1
        base, n = key, 2
        while Path(key).stem in used:                  # 그래도 겹치면 번호를 붙임
            key = f"{Path(base).stem}_{n}{Path(base).suffix}"
            n += 1
        used.add(Path(key).stem)
        items.append(ImageItem(p, key, source, split, dataset_dir, labels_dir))
    return Workspace(root, items, renamed)


# ==================================================
# 4. 라벨 찾기
# ==================================================

def get_label_stages(item):
    """이 이미지에 대해 실제로 존재하는 단계 목록.  예) {'Raw', 'Work'}"""
    return {s for s in STAGES if item.label_path(s).exists()}


def find_label_to_load(item):
    """
    화면에 띄울 라벨을 고릅니다. (WORK > FINAL > RAW)
    돌려주는 값: (단계, 경로)  /  라벨이 하나도 없으면 (None, None)
    """
    for stage in LOAD_PRIORITY:
        path = item.label_path(stage)
        if path.exists():
            return stage, path
    return None, None


def find_legacy_imports(items):
    """
    통합 폴더로 처음 한 번 '복사'해 올 라벨들을 찾습니다. (원래 파일은 그대로)
        Raw   : 데이터셋의 원래 라벨 (labels/train/a.txt) 또는 v2.x 의 labels/Raw/train/a.txt
        Work  : v2.x 때 데이터셋마다 만들던 labels/Work/train/a.txt
        Final : v2.x 때 데이터셋마다 만들던 labels/Final/train/a.txt
    돌려주는 값: [(복사할 파일, 통합 경로, 단계), ...]
    """
    pairs = []
    for it in items:
        raw_dst = it.label_path(STAGE_RAW)
        if not raw_dst.exists():
            for src in (it.original_label_path(), it.legacy_stage_path(STAGE_RAW)):
                if src.is_file() and src != raw_dst:
                    pairs.append((src, raw_dst, STAGE_RAW))
                    break
        # Work / Final 은 통합 폴더에 이 이미지 작업이 하나도 없을 때만 가져옵니다.
        if not (it.label_path(STAGE_WORK).exists() or it.label_path(STAGE_FINAL).exists()):
            for stage in (STAGE_WORK, STAGE_FINAL):
                src, dst = it.legacy_stage_path(stage), it.label_path(stage)
                if src.is_file() and src != dst:
                    pairs.append((src, dst, stage))
    return pairs


# ==================================================
# 5. YOLO TXT 읽기
# ==================================================

def read_yolo_file(label_path, img_w, img_h):
    """
    YOLO TXT → BBox 목록. (원본 이미지 픽셀 좌표로 변환해서 돌려줍니다)
    BBox 하나 = {"cls": 1, "x1": .., "y1": .., "x2": .., "y2": ..}
    잘못된 줄은 건너뛰고 줄 번호를 bad_lines 로 알려줍니다.
    """
    boxes, bad_lines = [], []
    if label_path is None or not os.path.exists(label_path):     # 아직 라벨이 없는 이미지
        return boxes, bad_lines

    # utf-8-sig: 윈도우 메모장이 붙이는 BOM 문자도 자동으로 제거
    with open(label_path, "r", encoding="utf-8-sig") as f:
        for line_no, line in enumerate(f, start=1):
            parts = line.split()
            if not parts:                       # 빈 줄
                continue
            if len(parts) != 5:
                bad_lines.append(line_no)
                continue
            try:
                class_id = int(parts[0])
                xc, yc, w, h = map(float, parts[1:])
            except ValueError:
                bad_lines.append(line_no)
                continue

            x1, y1, x2, y2 = yolo_to_bbox(xc, yc, w, h, img_w, img_h)
            # 이미지 밖으로 살짝 삐져나온 값은 테두리 안으로 정리
            x1, x2 = max(0.0, x1), min(float(img_w), x2)
            y1, y2 = max(0.0, y1), min(float(img_h), y2)
            if x2 - x1 <= 0 or y2 - y1 <= 0:
                bad_lines.append(line_no)
                continue
            boxes.append({"cls": class_id, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
    return boxes, bad_lines
