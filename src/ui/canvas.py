"""
canvas.py - 이미지 Canvas (그리기 · Zoom · Pan · 마우스)
=======================================================

좌표계가 두 개라는 것만 기억하면 나머지는 쉽습니다.

    원본 이미지 좌표 : 저장/계산용. BBox 는 항상 이 좌표로 보관
    Canvas(화면) 좌표 : 마우스 이벤트, 그리기용

    Canvas = 원본 × scale + offset
    원본   = (Canvas − offset) ÷ scale

Zoom 은 scale 을, Pan 은 offset 을 바꾸는 것뿐입니다.

이 Canvas 는 '무엇이 바뀌었는지'만 콜백으로 main_window 에 알려줍니다.
(오른쪽 패널, 상태 표시줄 갱신은 main_window 담당)
"""

import tkinter as tk

from PIL import Image, ImageTk

from src.bbox.bbox_editor import BBoxEditor, handle_positions, hit_box, hit_handle

# Pillow 9.1+ 는 Image.Resampling.BILINEAR, 예전 버전은 Image.BILINEAR → 둘 다 동작하게 처리
RESAMPLE = getattr(Image, "Resampling", Image)

FONT = "Malgun Gothic"
CANVAS_BG = "#2B2F36"
MIN_BOX_SIZE = 4      # 이보다 작게(화면 픽셀) 드래그하면 '클릭'으로 봅니다.
HANDLE_SIZE = 4       # 선택 BBox 모서리 핸들(□) 반지름
ZOOM_STEP = 1.25      # Zoom 한 번에 1.25배
MAX_SCALE = 20.0      # 최대 2000%

MODE_CURSORS = {"draw": "crosshair", "select": "arrow", "pan": "fleur"}
HANDLE_CURSORS = {"nw": "top_left_corner", "se": "bottom_right_corner",
                  "ne": "top_right_corner", "sw": "bottom_left_corner",
                  "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                  "e": "sb_h_double_arrow", "w": "sb_h_double_arrow"}


class ImageCanvas(tk.Canvas):
    """
    manager           : BBoxManager (BBox 데이터)
    class_style(id)   : → (이름, 색)   ※ 설정 파일을 직접 몰라도 되게 함수로 받습니다.
    get_class()       : → 새 BBox 에 쓸 현재 Class 번호
    on_select()       : 선택이 바뀌었을 때
    on_edit(message)  : BBox 가 추가/이동/크기 조절되었을 때
    on_live()         : 드래그 중 (오른쪽 정보 패널 실시간 갱신용)
    on_status(text)   : 상태 표시줄에 보여줄 글
    """

    def __init__(self, parent, manager, class_style, get_class,
                 on_select, on_edit, on_live, on_status, **kwargs):
        super().__init__(parent, bg=CANVAS_BG, highlightthickness=0, **kwargs)
        self.manager = manager
        self.editor = BBoxEditor(manager)
        self.class_style = class_style
        self.get_class = get_class
        self.on_select = on_select
        self.on_edit = on_edit
        self.on_live = on_live
        self.on_status = on_status

        self.pil_image = None        # 원본 PIL 이미지 (Zoom 할 때마다 여기서 잘라 씁니다)
        self.tk_image = None         # ⚠️ PhotoImage 참조를 붙잡아 둬야 화면에서 안 사라짐
        self.img_w = 0
        self.img_h = 0

        self.scale = 1.0
        self.off_x = 0.0
        self.off_y = 0.0
        self.fit_mode = True         # True면 창 크기가 바뀔 때 자동으로 다시 맞춤
        self.mode = "select"
        self.pan = None              # Pan 드래그 정보
        self.temp_rect = None        # 새 BBox 미리보기 사각형
        self.zoom_listener = None    # Zoom 배율이 바뀔 때 부를 함수 (main_window 가 지정)

        self.bind_mouse()

    # ==================================================
    # 1. 이미지 / 모드
    # ==================================================

    def set_image(self, pil_image):
        self.pil_image = pil_image
        self.img_w, self.img_h = pil_image.size
        self.editor.drag = None
        self.fit_to_window()

    def set_mode(self, mode):
        self.mode = mode
        self.config(cursor=MODE_CURSORS[mode])

    # ==================================================
    # 2. 좌표 변환
    # ==================================================

    def to_image(self, cx, cy):
        return (cx - self.off_x) / self.scale, (cy - self.off_y) / self.scale

    def to_canvas(self, ix, iy):
        return ix * self.scale + self.off_x, iy * self.scale + self.off_y

    def clamp(self, ix, iy):
        """원본 좌표를 이미지 안쪽(0 ~ w, 0 ~ h)으로 붙잡아 둡니다."""
        return min(max(ix, 0.0), float(self.img_w)), min(max(iy, 0.0), float(self.img_h))

    def event_to_image(self, event):
        return self.clamp(*self.to_image(event.x, event.y))

    def size(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1:                            # 창이 아직 화면에 안 그려졌을 때
            w, h = int(self["width"]), int(self["height"])
        return w, h

    # ==================================================
    # 3. 그리기
    # ==================================================

    def render(self):
        """이미지 + BBox 를 처음부터 다시 그립니다. (Zoom / Pan / 이미지 변경 시)"""
        self.delete("all")
        self.temp_rect = None
        cw, ch = self.size()

        if self.pil_image is None:
            self.create_text(cw / 2, ch / 2, fill="#9CA3AF", font=(FONT, 13), justify="center",
                             text="파일 > 폴더 열기 (Ctrl+O)\n\n프로젝트 데이터 폴더를 선택하세요.")
            return

        # 핵심 아이디어: 전체 이미지를 확대하지 않고 '화면에 보이는 부분만' 잘라서 확대
        # → 2000% 로 확대해도 메모리/속도 문제가 없습니다.
        s = self.scale
        x0, y0 = self.clamp(*self.to_image(0, 0))
        x1, y1 = self.clamp(*self.to_image(cw, ch))
        left, top = int(x0), int(y0)
        right, bottom = min(self.img_w, int(x1) + 1), min(self.img_h, int(y1) + 1)

        if right > left and bottom > top:
            region = self.pil_image.crop((left, top, right, bottom))
            disp_w = max(1, round((right - left) * s))
            disp_h = max(1, round((bottom - top) * s))
            # 크게 확대하면 픽셀이 또렷하게 보이도록 NEAREST, 평소엔 부드럽게 BILINEAR
            method = RESAMPLE.NEAREST if s >= 3 else RESAMPLE.BILINEAR
            region = region.resize((disp_w, disp_h), method)
            self.tk_image = ImageTk.PhotoImage(region)
            px, py = self.to_canvas(left, top)
            self.create_image(px, py, anchor="nw", image=self.tk_image, tags="image")

        self.draw_boxes()
        if self.zoom_listener:
            self.zoom_listener(self.scale)

    def draw_boxes(self):
        """BBox 만 다시 그립니다. (드래그 중에는 이미지까지 다시 그리면 느려서 분리)"""
        self.delete("box")
        boxes, selected = self.manager.boxes, self.manager.selected
        order = [i for i in range(len(boxes)) if i != selected]
        if selected is not None:
            order.append(selected)               # 선택된 BBox를 맨 위에

        for i in order:
            b = boxes[i]
            name, color = self.class_style(b["cls"])
            is_sel = (i == selected)
            cx1, cy1 = self.to_canvas(b["x1"], b["y1"])
            cx2, cy2 = self.to_canvas(b["x2"], b["y2"])
            self.create_rectangle(cx1, cy1, cx2, cy2, outline=color,
                                  width=3 if is_sel else 2, tags="box")

            # '2 나뭇가지류' 색깔 태그. 위쪽 공간이 없으면 박스 안쪽에 붙입니다.
            text = f"{b['cls']} {name}"
            if cy1 - 20 >= 0:
                tid = self.create_text(cx1 + 5, cy1 - 3, anchor="sw", text=text,
                                       fill="white", font=(FONT, 10, "bold"), tags="box")
            else:
                tid = self.create_text(cx1 + 5, cy1 + 3, anchor="nw", text=text,
                                       fill="white", font=(FONT, 10, "bold"), tags="box")
            tx1, ty1, tx2, ty2 = self.bbox(tid)
            bg_id = self.create_rectangle(tx1 - 5, ty1 - 1, tx2 + 5, ty2 + 1,
                                          fill=color, outline=color, tags="box")
            self.tag_raise(tid, bg_id)

            if is_sel:                           # 크기 조절용 핸들 8개
                for hx, hy in handle_positions(b, self.to_canvas).values():
                    self.create_rectangle(hx - HANDLE_SIZE, hy - HANDLE_SIZE,
                                          hx + HANDLE_SIZE, hy + HANDLE_SIZE,
                                          fill="white", outline=color, width=2, tags="box")

    # ==================================================
    # 4. Zoom / Pan
    # ==================================================

    def fit_scale(self):
        cw, ch = self.size()
        return min(cw / self.img_w, ch / self.img_h)

    def fit_to_window(self):
        if self.pil_image is None:
            return
        cw, ch = self.size()
        self.scale = self.fit_scale()
        self.off_x = (cw - self.img_w * self.scale) / 2     # 가운데 정렬
        self.off_y = (ch - self.img_h * self.scale) / 2
        self.fit_mode = True
        self.render()

    def zoom_at(self, factor, cx, cy):
        """(cx, cy) 지점을 고정한 채로 확대/축소 (마우스 아래 픽셀이 제자리에 남도록 offset 재계산)"""
        if self.pil_image is None:
            return
        new_scale = min(max(self.scale * factor, self.fit_scale() * 0.2), MAX_SCALE)
        if abs(new_scale - self.scale) < 1e-9:
            return
        self.off_x = cx - (cx - self.off_x) * new_scale / self.scale
        self.off_y = cy - (cy - self.off_y) * new_scale / self.scale
        self.scale = new_scale
        self.fit_mode = False
        self.render()

    def zoom_in(self):
        cw, ch = self.size()
        self.zoom_at(ZOOM_STEP, cw / 2, ch / 2)

    def zoom_out(self):
        cw, ch = self.size()
        self.zoom_at(1 / ZOOM_STEP, cw / 2, ch / 2)

    def start_pan(self, event):
        self.pan = (event.x, event.y)
        self.config(cursor="fleur")

    def do_pan(self, event):
        # 드래그 중에는 이미 그려진 것을 통째로 '옮기기'만 → 빠름
        dx, dy = event.x - self.pan[0], event.y - self.pan[1]
        self.move("all", dx, dy)
        self.off_x += dx
        self.off_y += dy
        self.pan = (event.x, event.y)

    def end_pan(self):
        self.pan = None
        self.fit_mode = False
        self.config(cursor=MODE_CURSORS[self.mode])
        self.render()                          # 놓았을 때 새로 보이는 영역까지 다시 그리기

    # ==================================================
    # 5. 마우스 이벤트
    # ==================================================

    def bind_mouse(self):
        self.bind("<ButtonPress-1>", self.on_left_down)
        self.bind("<B1-Motion>", self.on_left_drag)
        self.bind("<ButtonRelease-1>", self.on_left_up)
        self.bind("<Motion>", self.on_mouse_move)
        # 오른쪽·가운데 버튼 드래그: 언제든 Pan
        for n in (2, 3):
            self.bind(f"<ButtonPress-{n}>", self.on_pan_down)
            self.bind(f"<B{n}-Motion>", self.on_pan_drag)
            self.bind(f"<ButtonRelease-{n}>", self.on_pan_up)
        # 마우스 휠: Windows/Mac 은 <MouseWheel>, 리눅스는 Button-4/5
        self.bind("<MouseWheel>", self.on_wheel)
        self.bind("<Button-4>", self.on_wheel)
        self.bind("<Button-5>", self.on_wheel)
        self.bind("<Configure>", self.on_resize)

    def on_left_down(self, event):
        self.focus_set()                      # 입력칸 포커스를 빼서 단축키가 먹게
        if self.pil_image is None or self.pan is not None:
            return

        if self.mode == "pan":
            self.start_pan(event)
            return

        if self.mode == "select":
            handle = hit_handle(self.manager.selected_box, event.x, event.y, self.to_canvas)
            if handle:                                        # ① 핸들 → 크기 조절
                self.editor.begin_resize(handle)
                return
            idx = hit_box(self.manager.boxes, event.x, event.y, self.to_canvas)
            if idx is not None:                               # ② 박스 안 → 선택 + 이동
                self.editor.begin_move(idx, *self.to_image(event.x, event.y))
                self.on_select()
            else:                                             # ③ 빈 곳 → 선택 해제
                self.manager.select(None)
                self.on_select()
            return

        # mode == "draw": 이미지 안쪽에서만 시작
        ix, iy = self.event_to_image(event)
        self.editor.begin_draw(ix, iy, self.get_class())
        sx, sy = self.to_canvas(ix, iy)
        _, color = self.class_style(self.get_class())
        self.temp_rect = self.create_rectangle(sx, sy, sx, sy, outline=color, width=2,
                                               dash=(4, 2), tags="temp")

    def on_left_drag(self, event):
        if self.pan is not None:
            if self.mode == "pan":
                self.do_pan(event)
            return
        if not self.editor.active:
            return

        ix, iy = self.event_to_image(event)
        if self.editor.drag_type == "move":       # 이동은 이미지 밖 좌표도 필요 (clamp 는 editor 가)
            ix, iy = self.to_image(event.x, event.y)
        preview = self.editor.update(ix, iy, self.img_w, self.img_h)

        if preview is not None and self.temp_rect is not None:     # draw 미리보기
            sx, sy = self.to_canvas(preview[0], preview[1])
            ex, ey = self.to_canvas(preview[2], preview[3])
            self.coords(self.temp_rect, sx, sy, ex, ey)
        elif preview is None:                                       # move / resize
            self.draw_boxes()
            self.on_live()

    def on_left_up(self, event):
        if self.pan is not None:
            if self.mode == "pan":
                self.end_pan()
            return
        if not self.editor.active:
            return

        kind = self.editor.drag_type
        ix, iy = self.event_to_image(event)
        if kind == "move":
            ix, iy = self.to_image(event.x, event.y)
        if self.temp_rect is not None:
            self.delete(self.temp_rect)
            self.temp_rect = None

        result = self.editor.finish(ix, iy, MIN_BOX_SIZE / self.scale, self.img_w, self.img_h)

        if result["type"] == "click":
            # 너무 작으면 '클릭'으로 보고 → 그 자리 BBox 선택 (모드 전환 없이 빠르게 고르기)
            idx = hit_box(self.manager.boxes, event.x, event.y, self.to_canvas)
            self.manager.select(idx)
            self.on_select()
            if idx is None:
                self.on_status("BBox가 너무 작아서 무시했습니다.")
        elif result["type"] == "added":
            b = self.manager.selected_box
            name, _ = self.class_style(b["cls"])
            self.on_edit(f"[{b['cls']} {name}] BBox 추가 ({b['x1']:.0f}, {b['y1']:.0f}) ~ "
                         f"({b['x2']:.0f}, {b['y2']:.0f})  |  BBox {len(self.manager.boxes)}개")
        elif result["type"] == "move":
            self.on_edit("BBox 이동 완료")
        elif result["type"] == "resize":
            self.on_edit("BBox 크기 조절 완료")
        else:
            self.draw_boxes()

    def cancel_drag(self):
        """Esc. 진행 중인 드래그가 있었으면 True"""
        if self.temp_rect is not None:
            self.delete(self.temp_rect)
            self.temp_rect = None
        if self.editor.cancel():
            self.draw_boxes()
            self.on_live()
            return True
        return False

    def on_mouse_move(self, event):
        """선택 이동 모드에서 핸들/박스 위에 올리면 커서 모양을 바꿔 힌트를 줍니다."""
        if self.mode != "select" or self.editor.active or self.pan or self.pil_image is None:
            return
        handle = hit_handle(self.manager.selected_box, event.x, event.y, self.to_canvas)
        if handle:
            cursor = HANDLE_CURSORS[handle]
        elif hit_box(self.manager.boxes, event.x, event.y, self.to_canvas) is not None:
            cursor = "fleur"
        else:
            cursor = "arrow"
        self.config(cursor=cursor)

    def on_pan_down(self, event):
        if self.pil_image is not None and not self.editor.active and self.pan is None:
            self.start_pan(event)

    def on_pan_drag(self, event):
        if self.pan is not None:
            self.do_pan(event)

    def on_pan_up(self, event):
        if self.pan is not None:
            self.end_pan()

    def on_wheel(self, event):
        up = event.delta > 0 if event.num not in (4, 5) else event.num == 4
        self.zoom_at(ZOOM_STEP if up else 1 / ZOOM_STEP, event.x, event.y)

    def on_resize(self, event):
        if self.pil_image is not None and self.fit_mode:
            self.fit_to_window()
        else:
            self.render()
