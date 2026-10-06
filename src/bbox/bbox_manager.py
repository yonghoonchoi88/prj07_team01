"""
bbox_manager.py - BBox 데이터 관리 (생성 · 수정 · 삭제 · 되돌리기)
================================================================

화면(tkinter)을 전혀 모르는 '순수 데이터' 클래스입니다.
→ GUI 없이도 테스트할 수 있습니다.

BBox 하나 = {"cls": 1, "x1": .., "y1": .., "x2": .., "y2": ..}   (원본 이미지 픽셀 좌표)
"""

import copy

HISTORY_LIMIT = 50        # Ctrl+Z 되돌리기 최대 횟수


class BBoxManager:
    def __init__(self, history_limit=HISTORY_LIMIT):
        self.boxes = []          # 현재 이미지의 BBox 목록
        self.selected = None     # 선택된 BBox 번호 (없으면 None)
        self.history = []        # 되돌리기용 스냅샷
        self.dirty = False       # 저장 안 된 변경이 있는지
        self.history_limit = history_limit

    # ---------- 불러오기 / 저장 상태 ----------
    def load(self, boxes):
        """새 이미지의 BBox 로 통째로 교체 (되돌리기 기록도 초기화)"""
        self.boxes = boxes
        self.selected = None
        self.history = []
        self.dirty = False

    def mark_saved(self, boxes=None):
        """저장 직후 호출. 다시 읽은 BBox 가 있으면 화면 내용을 그걸로 맞춥니다."""
        if boxes is not None:
            self.boxes = boxes
            if self.selected is not None and self.selected >= len(self.boxes):
                self.selected = None
        self.dirty = False

    # ---------- 선택 ----------
    @property
    def selected_box(self):
        return None if self.selected is None else self.boxes[self.selected]

    def select(self, idx):
        if idx is not None and not (0 <= idx < len(self.boxes)):
            idx = None
        self.selected = idx

    # ---------- 되돌리기 ----------
    def snapshot(self):
        return copy.deepcopy(self.boxes)

    def push_history(self, snapshot=None):
        """변경 '직전' 상태를 저장 → Ctrl+Z 로 돌아갈 수 있게"""
        self.history.append(self.snapshot() if snapshot is None else snapshot)
        del self.history[:-self.history_limit]          # 오래된 것은 버림

    def commit(self, snapshot):
        """드래그(이동/크기 조절)처럼 '이미 바꾼 뒤'에 기록할 때 사용"""
        self.push_history(snapshot)
        self.dirty = True

    def undo(self):
        if not self.history:
            return False
        self.boxes = self.history.pop()
        self.selected = None
        self.dirty = True
        return True

    # ---------- 생성 / 수정 / 삭제 ----------
    def add(self, cls, x1, y1, x2, y2):
        self.push_history()
        self.boxes.append({"cls": cls, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        self.selected = len(self.boxes) - 1
        self.dirty = True
        return self.selected

    def replace(self, idx, box):
        self.push_history()
        self.boxes[idx] = dict(box)
        self.dirty = True

    def set_class(self, idx, cls):
        """Class 변경. 바뀌었으면 예전 Class 번호를, 그대로면 None 을 돌려줍니다."""
        box = self.boxes[idx]
        if box["cls"] == cls:
            return None
        old = box["cls"]
        self.push_history()
        box["cls"] = cls
        self.dirty = True
        return old

    def delete_selected(self):
        if self.selected is None:
            return None
        self.push_history()
        removed = self.boxes.pop(self.selected)
        self.selected = None
        self.dirty = True
        return removed

    def replace_all(self, boxes):
        """BBox 전체 교체 (예: RAW 원본으로 되돌리기). Ctrl+Z 로 취소 가능"""
        self.push_history()
        self.boxes = boxes
        self.selected = None
        self.dirty = True
