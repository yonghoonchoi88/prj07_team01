"""
yolo_loader.py - YOLO TXT 불러오기 (Load)
=========================================

[담당]
    - 폴더에서 이미지 목록 만들기
    - 이미지 경로 → RAW / WORK / FINAL 라벨 경로 계산
    - 지금 어떤 단계의 라벨을 읽어야 하는지 결정 (WORK > FINAL > RAW)
    - YOLO TXT → BBox 목록 (원본 픽셀 좌표)

[라벨 폴더 구조]
    이물검출_학습데이터1/
    ├─ images/train/a.jpg
    └─ labels/
       ├─ Raw/train/a.txt     ← 원본 (절대 수정 X)
       ├─ Work/train/a.txt    ← 작업 중 (저장하면 여기에 생김)
       └─ Final/train/a.txt   ← 검수 완료 (검수자가 저장하면 여기에만 저장)

이 파일은 '읽기'만 합니다. 디스크에 쓰는 일은 yolo_writer.py 담당입니다.
"""

import os
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
# 2. 이미지 목록
# ==================================================

def collect_images(folder):
    """
    선택한 폴더에서 이미지 목록을 만듭니다.
        - 폴더 안에 images/ 가 있으면 → images/ 아래(train, val ...) 전부
        - 선택한 폴더 이름이 images 면 → 그 아래 전부
        - 둘 다 아니면 → 선택한 폴더 바로 아래 이미지만 (Day 1 방식)
    돌려주는 값: (기준 폴더, 이미지 Path 목록)
    """
    folder = Path(folder)
    if (folder / "images").is_dir():
        root = folder / "images"
        candidates = root.rglob("*")
    elif folder.name == "images":
        root = folder
        candidates = root.rglob("*")
    else:
        root = folder
        candidates = root.iterdir()
    paths = sorted(p for p in candidates
                   if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    return root, paths


# ==================================================
# 3. 라벨 경로 (RAW / WORK / FINAL)
# ==================================================

def split_label_location(image_path):
    """
    이미지 경로 → (labels 폴더, labels 아래 상대 경로)

        .../images/train/a.jpg  →  (.../labels,           train/a.txt)
        .../my_images/a.jpg     →  (.../my_images/labels, a.txt)        ← Day 1 방식
    """
    p = Path(image_path)
    parts = list(p.parts)
    if "images" in parts[:-1]:
        idx = len(parts) - 1 - parts[::-1].index("images")    # 가장 마지막 'images'
        labels_root = Path(*parts[:idx]) / "labels"
        relative = Path(*parts[idx + 1:]).with_suffix(".txt")
    else:
        labels_root = p.parent / "labels"
        relative = Path(p.stem + ".txt")
    return labels_root, relative


def get_label_path(image_path, stage):
    """이미지 경로 + 단계 → 라벨 TXT 경로.  예) labels/Work/train/a.txt"""
    if stage not in STAGES:
        raise ValueError(f"알 수 없는 단계: {stage}")
    labels_root, relative = split_label_location(image_path)
    return labels_root / stage / relative


def get_legacy_label_path(image_path):
    """단계 폴더를 쓰기 전(Day 1~2)의 라벨 위치.  예) labels/train/a.txt"""
    labels_root, relative = split_label_location(image_path)
    return labels_root / relative


def get_label_stages(image_path):
    """이 이미지에 대해 실제로 존재하는 단계 목록.  예) {'Raw', 'Work'}"""
    return {s for s in STAGES if get_label_path(image_path, s).exists()}


def find_label_to_load(image_path):
    """
    화면에 띄울 라벨을 고릅니다. (WORK > FINAL > RAW)
    돌려주는 값: (단계, 경로)  /  라벨이 하나도 없으면 (None, None)
    """
    for stage in LOAD_PRIORITY:
        path = get_label_path(image_path, stage)
        if path.exists():
            return stage, path
    return None, None


def find_legacy_labels(image_paths):
    """
    예전 위치(labels/train/a.txt)에 라벨이 있는데 Raw 에는 아직 없는 것들을 찾습니다.
    → 처음 한 번 Raw 로 '복사'해서 원본으로 보관하기 위함
    돌려주는 값: [(예전 경로, Raw 경로), ...]
    """
    pairs = []
    for img in image_paths:
        legacy = get_legacy_label_path(img)
        raw = get_label_path(img, STAGE_RAW)
        if legacy.is_file() and not raw.exists():
            pairs.append((legacy, raw))
    return pairs


# ==================================================
# 4. YOLO TXT 읽기
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
