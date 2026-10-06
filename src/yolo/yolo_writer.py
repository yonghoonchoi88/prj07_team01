"""
yolo_writer.py - YOLO TXT 저장 (Save) - 역할별 저장 위치
=====================================================

[담당]
    - BBox 목록 → YOLO TXT
    - 역할(role)에 따라 저장 위치를 딱 하나로 정함
          작업자(worker)   → labels/Work  에만 저장
          검수자(reviewer) → labels/Final 에만 저장 (저장 후 Work 파일은 정리)
    - FINAL 은 WORK 를 거친 파일만 갈 수 있음 (RAW → FINAL 직행 금지)
    - 데이터셋의 원래 라벨 · v2.x 단계 폴더를 통합 폴더로 '복사' (처음 한 번, 덮어쓰기 X)

[안전 장치]
    RAW 는 원본 보관용입니다. write_yolo_file() 은 RAW 경로면 저장을 거부합니다.
    검수자 저장은 Work 에 파일이 있을 때만 됩니다. (save_for_role 이 직접 막음)
"""

import os
import shutil
from pathlib import Path

from src.yolo.yolo_loader import STAGE_FINAL, STAGE_RAW, STAGE_WORK


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


# ==================================================
# 2. TXT 쓰기
# ==================================================

def is_raw_path(path):
    """경로 안에 'labels/Raw' 가 들어 있으면 원본 폴더로 봅니다."""
    parts = Path(path).parts
    return any(parts[i] == "labels" and parts[i + 1] == STAGE_RAW for i in range(len(parts) - 1))


def format_yolo_lines(boxes, img_w, img_h):
    """BBox 목록 → YOLO TXT 한 줄씩 (문자열 목록). 저장 전에 validator 로 미리 검사할 때도 씁니다."""
    lines = []
    for b in boxes:
        xc, yc, w, h = bbox_to_yolo(b["x1"], b["y1"], b["x2"], b["y2"], img_w, img_h)
        lines.append(f"{b['cls']} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
    return lines


def write_yolo_file(label_path, boxes, img_w, img_h):
    """
    BBox 목록 → YOLO TXT. BBox 가 0개면 빈 파일(= '객체 없음' 검수 완료)이 됩니다.

    임시 파일에 먼저 다 쓴 다음 한 번에 바꿔치기(os.replace) 합니다.
    → 저장 도중 프로그램이 꺼져도 반쯤 쓰다 만 TXT 가 남지 않습니다.
    """
    if is_raw_path(label_path):
        raise PermissionError(f"RAW 폴더는 원본 보관용이라 저장할 수 없습니다.\n{label_path}")

    label_path = Path(label_path)
    label_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = label_path.with_suffix(".txt.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for line in format_yolo_lines(boxes, img_w, img_h):
            f.write(line + "\n")
    os.replace(tmp_path, label_path)


# ==================================================
# 3. 역할별 저장 (작업자 → Work / 검수자 → Final)
# ==================================================

# 역할 → 저장할 수 있는 단 하나의 단계
ROLE_WORKER = "worker"
ROLE_REVIEWER = "reviewer"
ROLE_STAGE = {ROLE_WORKER: STAGE_WORK, ROLE_REVIEWER: STAGE_FINAL}


def save_for_role(role, item, boxes, img_w, img_h):
    """
    역할에 맞는 폴더에만 저장합니다. 저장한 경로를 돌려줍니다.
        작업자 → Work
        검수자 → Final  (검수가 끝났으니 Work 파일은 지워서 'Work → Final 이동'과 같은 결과)

    ⚠ FINAL 은 반드시 WORK 를 거쳐야 합니다.
       Work 에 파일이 없는 이미지(RAW 만 있거나 라벨이 없는 이미지)는 검수자가 저장할 수 없습니다.
       → 화면 코드에서 실수로 막는 걸 빠뜨려도, 여기서 한 번 더 막습니다. (이중 안전장치)
    """
    if role not in ROLE_STAGE:
        raise PermissionError("작업자 또는 검수자를 먼저 선택해야 저장할 수 있습니다.")
    stage = ROLE_STAGE[role]
    work_path = item.label_path(STAGE_WORK)

    if stage == STAGE_FINAL and not can_move_to_final(item):
        raise PermissionError("WORK 에 없는 파일은 FINAL 로 옮길 수 없습니다.\n"
                              "작업자가 먼저 WORK 에 저장해야 검수할 수 있습니다.\n"
                              f"{work_path}")

    label_path = item.label_path(stage)
    write_yolo_file(label_path, boxes, img_w, img_h)

    if stage == STAGE_FINAL:
        os.remove(work_path)                # Work → Final 이동 완료
    return label_path


def can_move_to_final(item):
    """이 이미지를 FINAL 로 옮길 수 있나? = WORK 에 라벨 파일이 있나?"""
    return item.label_path(STAGE_WORK).is_file()


# ==================================================
# 4. 통합 폴더로 처음 한 번 복사
# ==================================================

def copy_into_workspace(pairs):
    """
    [(원래 파일, 통합 경로, 단계), ...] 를 받아 통합 폴더로 '복사'합니다.
    - 원래 파일은 그대로 둡니다. (move 가 아니라 copy)
    - 통합 폴더에 이미 파일이 있으면 절대 덮어쓰지 않습니다. (특히 Raw)
    돌려주는 값: {단계: 복사한 개수}
    """
    copied = {}
    for src, dst, stage in pairs:
        dst = Path(dst)
        if dst.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)                 # copy2: 수정 시각 같은 정보도 같이 복사
        copied[stage] = copied.get(stage, 0) + 1
    return copied
