"""
yolo_writer.py - YOLO TXT 저장 (Save) + work / final 정리
=========================================================

[담당]
    - BBox 목록 → YOLO TXT
    - 작업자(1차 검수) 저장   → data/work/labels/a.txt
    - 검수자 QA PASS          → data/final/labels/a.txt + data/final/images/a.jpg (한 쌍)
                                (QA 가 끝났으니 work 의 TXT 는 정리 = work → final 이동)
    - PASS 된 이미지를 다시 고치면 final 에서 빼기 (final 에는 QA PASS 데이터만 남아야 함)

[안전 장치]
    - raw(원본)에는 절대 쓰지 않습니다. 경로가 raw 쪽이면 저장을 거부합니다.
    - FINAL 은 work 를 거친 파일만 갈 수 있습니다. (raw → final 직행 금지)
    - 임시 파일에 먼저 쓰고 한 번에 바꿔치기 → 저장 도중 꺼져도 반쪽 TXT 가 남지 않음
"""

import os
import shutil
from pathlib import Path

from src.yolo.yolo_loader import STAGE_FINAL, STAGE_WORK

ROLE_WORKER = "worker"        # 1차 검수 작업자
ROLE_REVIEWER = "reviewer"    # 교차검수(QA) 검수자


# ==================================================
# 1. 좌표 변환 (픽셀 → YOLO)
# ==================================================

def bbox_to_yolo(x1, y1, x2, y2, img_w, img_h):
    """픽셀 좌표 (x1, y1, x2, y2) → YOLO (x_center, y_center, width, height), 모두 0~1"""
    x_center = (x1 + x2) / 2 / img_w
    y_center = (y1 + y2) / 2 / img_h
    width = (x2 - x1) / img_w
    height = (y2 - y1) / img_h
    return x_center, y_center, width, height


def format_yolo_lines(boxes, img_w, img_h):
    """BBox 목록 → YOLO TXT 한 줄씩 (문자열 목록). 저장 전에 validator 로 미리 검사할 때도 씁니다."""
    lines = []
    for b in boxes:
        xc, yc, w, h = bbox_to_yolo(b["x1"], b["y1"], b["x2"], b["y2"], img_w, img_h)
        lines.append(f"{b['cls']} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
    return lines


# ==================================================
# 2. TXT 쓰기
# ==================================================

def write_yolo_file(label_path, boxes, img_w, img_h, ws=None):
    """
    BBox 목록 → YOLO TXT. BBox 가 0개면 빈 파일(= '검출 대상 없음')이 됩니다.
    ws(작업 공간)를 주면 raw 경로인지 확인해서 막습니다.
    """
    label_path = Path(label_path)
    if ws is not None and ws.is_raw(label_path):
        raise PermissionError(f"raw 폴더는 원본 보관용이라 저장할 수 없습니다.\n{label_path}")

    label_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = label_path.with_suffix(".txt.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for line in format_yolo_lines(boxes, img_w, img_h):
            f.write(line + "\n")
    os.replace(tmp_path, label_path)


# ==================================================
# 3. work / final
# ==================================================

def is_in_final(item):
    return item.label_path(STAGE_FINAL).is_file() or item.final_image_path.is_file()


def remove_from_final(item):
    """final 에서 이 이미지의 TXT · 이미지 복사본을 뺍니다. (원본 raw 는 그대로)  뺐으면 True"""
    removed = False
    for p in (item.label_path(STAGE_FINAL), item.final_image_path):
        if p.is_file():
            os.remove(p)
            removed = True
    return removed


def save_work(item, boxes, img_w, img_h):
    """
    work 에 저장. 이미 final 에 있던 이미지라면 final 에서 뺍니다. (다시 QA 를 받아야 하므로)
    돌려주는 값: (저장 경로, final 에서 뺐는지)
    """
    path = item.label_path(STAGE_WORK)
    write_yolo_file(path, boxes, img_w, img_h, item.ws)
    revoked = remove_from_final(item)
    return path, revoked


def can_move_to_final(item):
    """
    FINAL 로 보낼 수 있나?  (raw → final 직행 금지)
        - work 에 1차 검수 결과가 있거나
        - 이미 QA PASS 되어 final 에 있는 이미지 (검수자가 다시 확인 · 수정하는 경우)
    final 에는 work 를 거친 파일만 들어가므로, 두 경우 모두 '1차 검수를 거친' 파일입니다.
    """
    return item.label_path(STAGE_WORK).is_file() or item.label_path(STAGE_FINAL).is_file()


def pass_to_final(item, boxes, img_w, img_h):
    """
    QA PASS: final/labels 에 TXT, final/images 에 이미지(복사)를 한 쌍으로 저장하고
    work 의 TXT 는 정리합니다.   돌려주는 값: final TXT 경로
    """
    if not can_move_to_final(item):
        raise PermissionError("work 에 없는 파일은 FINAL 로 보낼 수 없습니다.\n"
                              "작업자가 먼저 1차 검수(work 저장)를 해야 합니다.")
    label_path = item.label_path(STAGE_FINAL)
    write_yolo_file(label_path, boxes, img_w, img_h, item.ws)

    img_dst = item.final_image_path
    img_dst.parent.mkdir(parents=True, exist_ok=True)
    if not img_dst.exists():
        shutil.copy2(item.path, img_dst)            # 원본 이미지는 그대로, 복사본만 final 로

    work_path = item.label_path(STAGE_WORK)
    if work_path.is_file():
        os.remove(work_path)                         # work → final 이동 완료
    return label_path
