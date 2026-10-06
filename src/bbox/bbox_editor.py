"""
bbox_editor.py - 마우스로 BBox 그리기 · 이동 · 크기 조절
=======================================================

canvas.py 가 마우스 좌표를 '원본 이미지 좌표'로 바꿔서 넘겨주면,
여기서 BBoxManager 의 데이터를 실제로 바꿉니다.

    canvas.py     : 어디를 눌렀나? (화면 좌표, 그리기)
    bbox_editor   : 그래서 BBox 를 어떻게 바꾸나? (드래그 상태 관리)
    bbox_manager  : BBox 목록 자체 (저장 대상 데이터)
"""

HANDLE_HIT = 7        # 핸들을 잡았다고 인정하는 거리 (화면 픽셀)
HIT_MARGIN = 3        # 박스 테두리 바깥 3px 까지는 클릭으로 인정


# ==================================================
# 1. 클릭 판정 (to_canvas: 원본 좌표 → 화면 좌표 함수)
# ==================================================

def handle_positions(box, to_canvas):
    """선택 BBox 의 핸들 8개 위치 (화면 좌표). 이름의 n/s/e/w = 북/남/동/서"""
    x1, y1 = to_canvas(box["x1"], box["y1"])
    x2, y2 = to_canvas(box["x2"], box["y2"])
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    return {"nw": (x1, y1), "n": (mx, y1), "ne": (x2, y1), "e": (x2, my),
            "se": (x2, y2), "s": (mx, y2), "sw": (x1, y2), "w": (x1, my)}


def hit_handle(box, x, y, to_canvas):
    """(x, y) 화면 좌표가 핸들 위면 핸들 이름, 아니면 None"""
    if box is None:
        return None
    for name, (hx, hy) in handle_positions(box, to_canvas).items():
        if abs(x - hx) <= HANDLE_HIT and abs(y - hy) <= HANDLE_HIT:
            return name
    return None


def hit_box(boxes, x, y, to_canvas):
    """클릭 위치를 포함하는 BBox 중 '가장 작은 것'의 번호 (큰 박스 안의 작은 박스 선택용)"""
    best, best_area = None, None
    for i, b in enumerate(boxes):
        x1, y1 = to_canvas(b["x1"], b["y1"])
        x2, y2 = to_canvas(b["x2"], b["y2"])
        if x1 - HIT_MARGIN <= x <= x2 + HIT_MARGIN and y1 - HIT_MARGIN <= y <= y2 + HIT_MARGIN:
            area = (x2 - x1) * (y2 - y1)
            if best is None or area < best_area:
                best, best_area = i, area
    return best


# ==================================================
# 2. 드래그 편집기
# ==================================================

class BBoxEditor:
    """
    드래그 한 번 = begin_xxx() → update() 여러 번 → finish()
    모든 좌표는 '원본 이미지 좌표'입니다.
    """

    def __init__(self, manager):
        self.manager = manager
        self.drag = None          # 진행 중인 드래그 정보 (없으면 None)

    @property
    def active(self):
        return self.drag is not None

    @property
    def drag_type(self):
        return None if self.drag is None else self.drag["type"]

    # ---------- 시작 ----------
    def begin_draw(self, ix, iy, cls):
        self.drag = {"type": "draw", "ix": ix, "iy": iy, "cls": cls}

    def begin_move(self, idx, ix, iy):
        self.manager.select(idx)
        self.drag = {"type": "move", "ix": ix, "iy": iy,
                     "orig": dict(self.manager.boxes[idx]),
                     "snapshot": self.manager.snapshot()}

    def begin_resize(self, handle):
        self.drag = {"type": "resize", "handle": handle,
                     "orig": dict(self.manager.selected_box),
                     "snapshot": self.manager.snapshot()}

    # ---------- 드래그 중 ----------
    def update(self, ix, iy, img_w, img_h):
        """
        draw   : 미리보기 사각형 (x1, y1, x2, y2) 를 돌려줌 (데이터는 아직 안 바꿈)
        move   : 선택 BBox 를 이동 (이미지 밖으로는 못 나가게)
        resize : 잡은 핸들 쪽 변만 이동
        """
        d = self.drag
        if d is None:
            return None

        if d["type"] == "draw":
            return d["ix"], d["iy"], ix, iy

        b = self.manager.selected_box
        if d["type"] == "move":
            o = d["orig"]
            w, h = o["x2"] - o["x1"], o["y2"] - o["y1"]
            nx1 = min(max(o["x1"] + (ix - d["ix"]), 0.0), img_w - w)
            ny1 = min(max(o["y1"] + (iy - d["iy"]), 0.0), img_h - h)
            b.update(x1=nx1, y1=ny1, x2=nx1 + w, y2=ny1 + h)

        elif d["type"] == "resize":
            h = d["handle"]
            if "w" in h: b["x1"] = ix
            if "e" in h: b["x2"] = ix
            if "n" in h: b["y1"] = iy
            if "s" in h: b["y2"] = iy
        return None

    # ---------- 끝 ----------
    def finish(self, ix, iy, min_size, img_w, img_h):
        """
        드래그를 마무리하고 무슨 일이 있었는지 dict 로 알려줍니다.
            {"type": "click"}                → 너무 작게 드래그 = 클릭
            {"type": "added", "idx": 3}      → 새 BBox 추가
            {"type": "move" / "resize"}      → 이동 / 크기 조절 완료
            {"type": "none"}                 → 바뀐 게 없음
        min_size: 이보다 작으면 클릭으로 봄 (원본 좌표 기준)
        """
        d, self.drag = self.drag, None
        if d is None:
            return {"type": "none"}

        if d["type"] == "draw":
            x1, x2 = sorted((d["ix"], ix))     # 어느 방향으로 드래그해도 (왼쪽위, 오른쪽아래)
            y1, y2 = sorted((d["iy"], iy))
            if x2 - x1 < min_size or y2 - y1 < min_size:
                return {"type": "click"}
            idx = self.manager.add(d["cls"], x1, y1, x2, y2)
            return {"type": "added", "idx": idx}

        # move / resize 마무리
        b = self.manager.selected_box
        b["x1"], b["x2"] = sorted((b["x1"], b["x2"]))     # 핸들을 반대편으로 넘긴 경우 정리
        b["y1"], b["y2"] = sorted((b["y1"], b["y2"]))
        if b["x2"] - b["x1"] < 1:
            b["x2"] = min(float(img_w), b["x1"] + 1)
        if b["y2"] - b["y1"] < 1:
            b["y2"] = min(float(img_h), b["y1"] + 1)

        if b != d["orig"]:                                  # 실제로 바뀐 경우만 기록
            self.manager.commit(d["snapshot"])
            return {"type": d["type"]}
        return {"type": "none"}

    def cancel(self):
        """Esc: 그리던 BBox 취소. 이동/크기 조절 중이면 원래대로 되돌림"""
        d, self.drag = self.drag, None
        if d is None:
            return False
        if d["type"] in ("move", "resize"):
            self.manager.boxes = d["snapshot"]
        return True
