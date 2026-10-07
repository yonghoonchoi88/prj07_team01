"""
yolo_loader.py - 작업 폴더(data) 구성 + YOLO TXT 불러오기 (Load)
================================================================

[담당]
    - data 폴더 아래 '모든' 원본 이미지를 찾아 하나의 작업 목록(900장)으로 묶기
    - 이미지마다 출처(source_dataset)와 원래 위치(original_split) 계산
    - raw / work / final 라벨 경로 계산
    - 지금 어떤 라벨을 화면에 띄울지 결정 (work > final > raw)
    - YOLO TXT → BBox 목록 (원본 픽셀 좌표)

[폴더 구조]  교과7 산출물 기준.  data 폴더 하나만 열면 됩니다.
    data/
    ├─ raw/                                ← 원본 (절대 수정 X) : 받은 데이터셋 폴더를 그대로 넣기
    │   ├─ 이물검출_학습데이터1/images/train/a.jpg
    │   │                    └ labels/train/a.txt
    │   └─ 이물검출_학습데이터2/images/validation/b.jpg ...
    ├─ work/labels/a.txt                   ← 1차 검수 결과 (작업자 저장)
    ├─ final/images/a.jpg                  ← QA PASS (검수자) : 이미지 + TXT 한 쌍
    │   final/labels/a.txt
    └─ manifests/
        ├─ dataset_manifest.csv            ← 이미지 1장 = 1줄 작업대장
        ├─ label_history.csv               ← 누가 언제 무엇을 했는지
        └─ validation_runs.csv             ← Validation 실행 기록

    data/raw 가 없으면 data 아래 전체(work · final · manifests 제외)를 원본으로 봅니다.

이 파일은 '읽기'만 합니다. 디스크에 쓰는 일은 yolo_writer.py 담당입니다.
"""

import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# ---------- 라벨 단계 (data 아래 폴더 이름) ----------
STAGE_RAW = "raw"
STAGE_WORK = "work"
STAGE_FINAL = "final"
STAGES = (STAGE_RAW, STAGE_WORK, STAGE_FINAL)

# 화면을 열 때 어떤 라벨을 보여줄지 우선순위
#   work  : 1차 검수 결과가 있으면 그게 최신
#   final : QA PASS 된 이미지
#   raw   : 아직 아무도 손대지 않은 원본
LOAD_PRIORITY = (STAGE_WORK, STAGE_FINAL, STAGE_RAW)

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")
WORKSPACE_DIRS = ("work", "final", "manifests")      # 프로그램이 만드는 폴더 (원본 검색에서 제외)


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
# 2. 작업 공간 / 이미지 한 장의 정보
# ==================================================

class Workspace:
    """선택한 data 폴더 하나 = 작업 공간 하나"""

    def __init__(self, root):
        self.root = Path(root)
        raw = self.root / STAGE_RAW
        self.raw_dir = raw if raw.is_dir() else self.root      # 원본을 찾을 곳
        self.work_dir = self.root / STAGE_WORK
        self.final_dir = self.root / STAGE_FINAL
        self.manifest_dir = self.root / "manifests"
        self.items = []
        self.renamed = 0          # 파일명이 겹쳐서 이름 앞에 출처를 붙인 이미지 수

    @property
    def manifest_path(self):
        return self.manifest_dir / "dataset_manifest.csv"

    @property
    def history_path(self):
        return self.manifest_dir / "label_history.csv"

    @property
    def runs_path(self):
        return self.manifest_dir / "validation_runs.csv"

    @property
    def datasets(self):
        return sorted({it.source_dataset for it in self.items})

    def is_raw(self, path):
        """이 경로가 원본(raw) 쪽이면 True → 절대 쓰면 안 됨"""
        try:
            Path(path).resolve().relative_to(self.raw_dir.resolve())
        except ValueError:
            return False
        # raw 폴더가 없어서 data 전체를 원본으로 볼 때는 work / final / manifests 는 원본이 아님
        rel = Path(path).resolve().relative_to(self.raw_dir.resolve()).parts
        return not (self.raw_dir == self.root and rel and rel[0] in WORKSPACE_DIRS)


@dataclass
class ImageItem:
    """
    이미지 한 장 = 실제 파일 위치 + 통합 이름 + 출처 정보

        path            : 원본 이미지     (data/raw/이물검출_학습데이터2/images/train/b.jpg)
        key             : 통합 파일명     (b.jpg)  ← work/final 의 이름, manifest 의 file_name
        source_dataset  : 출처 데이터셋   (dataset2)
        original_split  : 기존 split      (train)
        dataset_dir     : 데이터셋 폴더   (data/raw/이물검출_학습데이터2)
        ws              : 작업 공간
    """
    path: Path
    key: str
    source_dataset: str
    original_split: str
    dataset_dir: Path
    ws: Workspace

    @property
    def label_name(self):
        return Path(self.key).stem + ".txt"

    def label_path(self, stage):
        """단계별 라벨 경로.  raw 는 데이터셋 안의 원래 TXT, work / final 은 통합 폴더"""
        if stage == STAGE_RAW:
            return self.dataset_dir / "labels" / self.original_split / (self.path.stem + ".txt")
        if stage == STAGE_WORK:
            return self.ws.work_dir / "labels" / self.label_name
        if stage == STAGE_FINAL:
            return self.ws.final_dir / "labels" / self.label_name
        raise ValueError(f"알 수 없는 단계: {stage}")

    @property
    def final_image_path(self):
        """final/images/ 에 복사될 이미지 경로 (TXT 와 기본 이름이 같아야 함)"""
        return self.ws.final_dir / "images" / (Path(self.key).stem + self.path.suffix.lower())

    @property
    def origin_text(self):
        """화면 표시용.  예) dataset2 · train"""
        return " · ".join(t for t in (self.source_dataset, self.original_split) if t)


# ==================================================
# 3. data 폴더 → 작업 공간 만들기
# ==================================================

def dataset_label(folder_name):
    """'이물검출_학습데이터2' → 'dataset2'  (끝에 숫자가 없으면 폴더 이름 그대로)"""
    m = re.search(r"(\d+)\s*$", folder_name)
    return f"dataset{int(m.group(1))}" if m else folder_name


def build_workspace(folder):
    """
    원본 폴더(data/raw, 없으면 data) 아래 하위 폴더 전체에서 이미지를 모읍니다.
    labels 폴더와 프로그램이 만드는 work · final · manifests 폴더는 건너뜁니다.
    """
    ws = Workspace(folder)
    base = ws.raw_dir
    found = []
    for p in sorted(base.rglob("*")):
        if not (p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS):
            continue
        rel = p.relative_to(base).parts
        if "labels" in rel[:-1]:
            continue
        if base == ws.root and rel[0] in WORKSPACE_DIRS:
            continue

        if "images" in rel[:-1]:
            # .../<데이터셋>/images/<split>/a.jpg
            idx = len(rel) - 2 - rel[:-1][::-1].index("images")
            ds_parts, split_parts = rel[:idx], rel[idx + 1:-1]
        else:
            # images 폴더가 없으면 이미지가 있는 폴더 자체를 데이터셋으로 봅니다.
            ds_parts, split_parts = rel[:-1], ()
        dataset_dir = base.joinpath(*ds_parts) if ds_parts else base
        source = dataset_label(ds_parts[-1] if ds_parts else ws.root.name)
        found.append((p, source, "/".join(split_parts), dataset_dir))

    # 통합 폴더에 모이면 파일명이 겹칠 수 있음 → 겹치는 것만 앞에 출처를 붙입니다.
    stem_count = Counter(p.stem for p, *_ in found)
    used = set()
    for p, source, split, dataset_dir in found:
        key = p.name
        if stem_count[p.stem] > 1:
            prefix = "_".join(t for t in (source, split.replace("/", "_")) if t)
            key = f"{prefix}__{p.name}"
            ws.renamed += 1
        base_key, n = key, 2
        while Path(key).stem in used:                  # 그래도 겹치면 번호를 붙임
            key = f"{Path(base_key).stem}_{n}{Path(base_key).suffix}"
            n += 1
        used.add(Path(key).stem)
        ws.items.append(ImageItem(p, key, source, split, dataset_dir, ws))
    return ws


# ==================================================
# 4. 라벨 찾기
# ==================================================

def find_label_to_load(item):
    """
    화면에 띄울 라벨을 고릅니다. (work > final > raw)
    돌려주는 값: (단계, 경로)  /  라벨이 하나도 없으면 (None, None)
    """
    for stage in LOAD_PRIORITY:
        path = item.label_path(stage)
        if path.exists():
            return stage, path
    return None, None


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


def label_signature(boxes, img_w, img_h, digits=4):
    """
    BBox 목록 → 비교용 '지문' (순서와 아주 작은 오차는 무시)
    DONE(원본 그대로) / EDITED(원본에서 바뀜) 판정에 씁니다.
    """
    sig = []
    for b in boxes:
        xc = (b["x1"] + b["x2"]) / 2 / img_w
        yc = (b["y1"] + b["y2"]) / 2 / img_h
        w = (b["x2"] - b["x1"]) / img_w
        h = (b["y2"] - b["y1"]) / img_h
        sig.append((b["cls"], round(xc, digits), round(yc, digits), round(w, digits), round(h, digits)))
    return sorted(sig)
