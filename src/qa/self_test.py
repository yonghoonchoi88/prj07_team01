"""
self_test.py - 프로그램 자동 테스트 (교과7 9번 Test Report 의 Golden / Pilot)
==========================================================================

실제 이미지와 TXT 로 '프로그램 기능'이 맞게 동작하는지 확인합니다.
(데이터가 맞는지는 QA Summary, 프로그램이 맞는지는 Test Report)

    - 실제 데이터는 절대 바꾸지 않습니다. 저장 · Reload 는 임시 폴더에서만 합니다.
    - 화면(마우스) 대신, 화면이 실제로 쓰는 코드(BBoxManager, ImageCanvas 좌표 변환,
      YOLO 저장/읽기, Validator)를 그대로 불러서 검사합니다.

테스트 항목 (교과7 Golden Test 표와 같은 순서)
    이미지 열기 / 기존 YOLO TXT Load / 기존 BBox 표시(좌표 변환) / BBox 추가 / BBox 수정 /
    BBox 삭제 / Class 변경 / Zoom / Pan / YOLO TXT 저장 / 저장 후 Reload / Validation
"""

import copy
import tempfile
import time
from pathlib import Path

from PIL import Image

from src.bbox.bbox_manager import BBoxManager
from src.ui.canvas import ImageCanvas
from src.yolo.yolo_loader import STAGE_RAW, read_yolo_file, yolo_to_bbox
from src.yolo.yolo_writer import bbox_to_yolo, write_yolo_file

TESTS = ["이미지 열기", "기존 YOLO TXT Load", "기존 BBox 표시 (좌표 변환)", "BBox 추가", "BBox 수정",
         "BBox 삭제", "Class 변경", "Zoom", "Pan", "YOLO TXT 저장", "저장 후 Reload", "Validation"]
PROGRAM_CHECKS = ("format", "bbox_bounds")      # 프로그램이 만든 TXT 에서 나오면 안 되는 오류


class _View:
    """화면 없이 ImageCanvas 의 좌표 변환 · Zoom 코드를 그대로 쓰기 위한 가짜 화면"""
    to_image = ImageCanvas.to_image
    to_canvas = ImageCanvas.to_canvas
    zoom_at = ImageCanvas.zoom_at

    def __init__(self, w, h):
        self.pil_image, self.img_w, self.img_h = True, w, h
        self.scale, self.off_x, self.off_y, self.fit_mode = 820 / w, 12.0, 34.0, True

    def fit_scale(self):
        return 820 / self.img_w

    def render(self):
        pass


def pick_sample(items, n, offset=0):
    """데이터셋 · split 이 고루 섞이도록 간격을 두고 n장 고르기 (항상 같은 결과)"""
    if not items:
        return []
    n = min(n, len(items))
    step = len(items) / n
    return [items[(int(i * step) + offset) % len(items)] for i in range(n)]


def _close(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def check_one(item, classes, validator, tmp_dir):
    """이미지 한 장으로 12개 항목 검사. 돌려주는 값: {테스트 이름: (통과 여부, 메모)}"""
    r = {}
    enabled = [c["id"] for c in classes if c["enabled"]]

    try:
        with Image.open(item.path) as im:
            im.load()
            w, h = im.size
        r["이미지 열기"] = (True, f"{w}x{h}")
    except OSError as e:
        return {t: (False, f"이미지를 열 수 없음: {e}") for t in TESTS}

    raw = item.label_path(STAGE_RAW)
    boxes, bad = read_yolo_file(raw, w, h)
    r["기존 YOLO TXT Load"] = (raw.is_file() and not bad,
                              "원본 TXT 없음" if not raw.is_file() else (f"형식 오류 줄 {bad}" if bad else f"BBox {len(boxes)}개"))

    # 화면에 그리는 픽셀 좌표 ↔ YOLO 좌표 왕복이 정확한가 (이미지 안쪽 BBox 만)
    ok = True
    if raw.is_file():
        for line in raw.read_text(encoding="utf-8-sig").splitlines():
            p = line.split()
            if len(p) != 5:
                continue
            try:
                v = tuple(map(float, p[1:]))
            except ValueError:
                continue
            x1, y1, x2, y2 = yolo_to_bbox(*v, w, h)
            if x1 >= 0 and y1 >= 0 and x2 <= w and y2 <= h:
                ok &= _close(bbox_to_yolo(x1, y1, x2, y2, w, h), v, 1e-9)
    r["기존 BBox 표시 (좌표 변환)"] = (ok, "")

    m = BBoxManager()
    m.load(copy.deepcopy(boxes))
    n0 = len(m.boxes)
    idx = m.add(enabled[0], w * 0.40, h * 0.40, w * 0.45, h * 0.46)
    r["BBox 추가"] = (len(m.boxes) == n0 + 1 and m.selected == idx, "")
    before = dict(m.boxes[idx])
    m.replace(idx, {**before, "x1": before["x1"] + 7, "x2": before["x2"] + 7})
    r["BBox 수정"] = (m.boxes[idx]["x1"] == before["x1"] + 7 and m.dirty, "")
    m.select(idx)
    m.delete_selected()
    r["BBox 삭제"] = (len(m.boxes) == n0, "")
    target = m.boxes[0] if m.boxes else None
    if target is None:
        m.add(enabled[0], w * 0.1, h * 0.1, w * 0.2, h * 0.2)
    new_cls = next(c for c in enabled if c != m.boxes[0]["cls"]) if len(enabled) > 1 else enabled[0]
    old = m.set_class(0, new_cls)
    r["Class 변경"] = ((old is not None or len(enabled) == 1) and m.boxes[0]["cls"] == new_cls, "")
    m.undo()                                           # Class 변경 되돌리기 (Ctrl+Z) 까지 확인
    if target is None:
        m.undo()
    r["Class 변경"] = (r["Class 변경"][0] and len(m.boxes) == n0, "Ctrl+Z 포함")

    # Zoom : 마우스 아래 지점이 확대/축소 후에도 그대로인가 + BBox 좌표 왕복
    v = _View(w, h)
    cx, cy = 400.0, 260.0
    anchor = v.to_image(cx, cy)
    ok = True
    for f in (1.25, 1.25, 1.25, 4.0, 4.0, 0.5, 0.8):
        v.zoom_at(f, cx, cy)
        ok &= _close(v.to_image(cx, cy), anchor, 1e-6)
        for b in boxes[:5]:
            ok &= _close(v.to_image(*v.to_canvas(b["x1"], b["y1"])), (b["x1"], b["y1"]), 1e-6)
    r["Zoom"] = (ok, f"최대 {v.scale * 100:.0f}%")

    # Pan : 화면을 dx, dy 만큼 옮기면 원본 좌표는 그대로, 화면 좌표만 dx, dy 이동
    ok = True
    for dx, dy in ((35, -12), (-200, 90), (3, 3)):
        p_before = v.to_canvas(*anchor)
        v.off_x += dx
        v.off_y += dy
        ok &= _close(v.to_canvas(*anchor), (p_before[0] + dx, p_before[1] + dy), 1e-6)
        ok &= _close(v.to_image(*v.to_canvas(*anchor)), anchor, 1e-6)
    r["Pan"] = (ok, "")

    # 저장 → Reload (임시 폴더)
    m.add(enabled[-1], w * 0.6, h * 0.6, w * 0.63, h * 0.65)      # 수정된 상태를 저장해 봄
    out = Path(tmp_dir) / "labels" / (Path(item.key).stem + ".txt")
    try:
        write_yolo_file(out, m.boxes, w, h)
        r["YOLO TXT 저장"] = (out.is_file(), "")
    except OSError as e:
        r["YOLO TXT 저장"] = (False, str(e))
    back, bad2 = read_yolo_file(out, w, h)
    same = len(back) == len(m.boxes) and not bad2 and all(
        a["cls"] == b["cls"] and all(abs(a[k] - b[k]) < 0.5 for k in ("x1", "y1", "x2", "y2"))
        for a, b in zip(back, m.boxes))
    r["저장 후 Reload"] = (same, f"BBox {len(back)}개")

    lines = out.read_text(encoding="utf-8").splitlines() if out.is_file() else []
    _, errors, _ = validator.parse_lines(lines)
    program_errors = [m_ for c, m_ in errors if c in PROGRAM_CHECKS]
    data_errors = sorted({c for c, _ in errors if c not in PROGRAM_CHECKS})
    r["Validation"] = (not program_errors,
                       "; ".join(program_errors) or (f"데이터 확인 필요: {', '.join(data_errors)}" if data_errors else ""))
    return r


def run_tests(items, n, classes, validator, offset=0):
    """
    n장으로 전체 항목 실행.
    돌려주는 값: {"n", "seconds", "per_test": {이름: 통과 수}, "fails": [(파일, 테스트, 메모)],
                 "image_pass": 모든 항목 통과한 이미지 수, "notes": [(파일, 메모)]}
    """
    sample = pick_sample(items, n, offset)
    start = time.time()
    per_test = {t: 0 for t in TESTS}
    fails, notes, image_pass = [], [], 0
    with tempfile.TemporaryDirectory(prefix="labeling_test_") as tmp:
        for it in sample:
            res = check_one(it, classes, validator, tmp)
            all_ok = True
            for t in TESTS:
                ok, memo = res.get(t, (False, "실행 안 됨"))
                per_test[t] += ok
                if not ok:
                    fails.append((it.key, t, memo))
                    all_ok = False
                elif t == "Validation" and memo:
                    notes.append((it.key, memo))
            image_pass += all_ok
    return {"n": len(sample), "seconds": round(time.time() - start, 1), "per_test": per_test,
            "fails": fails, "notes": notes, "image_pass": image_pass,
            "run_at": time.strftime("%Y-%m-%d %H:%M:%S")}
