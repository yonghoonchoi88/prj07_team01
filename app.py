"""
조각김치 이물검출 라벨링 프로그램 - Day 2
=========================================

Day 1 Mini Labeling Tool을 교재 7 [2일차] 화면에 맞춰 확장한 버전입니다.

    ① 폴더 선택 ─▶ ② 이미지·TXT 자동 로드 ─▶ ③ 기존 BBox 표시
        ─▶ ④ BBox 추가/수정/삭제 ─▶ ⑤ Class 변경 ─▶ ⑥ 저장 ─▶ ⑦ 다시 불러와 확인

[설치]
    pip install pillow

[폴더 구조] - 둘 다 지원합니다.
    (A) YOLO 프로젝트 폴더를 선택한 경우 (권장)
        이물검출_학습데이터1/
        ├─ images/train/250424_153512_001.jpg
        └─ labels/train/250424_153512_001.txt      ← images → labels 로 바꾼 같은 위치

    (B) 이미지가 바로 들어 있는 폴더를 선택한 경우 (Day 1 방식)
        my_images/sample_001.jpg  →  my_images/labels/sample_001.txt

[마우스]
    왼쪽 드래그          : (새 BBox 모드) BBox 그리기 / (선택 이동 모드) 이동·크기 조절
    오른쪽(가운데) 드래그 : 어떤 모드에서든 Pan (화면 이동)
    휠                   : 마우스 위치 기준 Zoom In / Out

[단축키]
    A / D          이전 / 다음 이미지          Ctrl+S       저장
    W / E / H      새 BBox / 선택 이동 / Pan    Ctrl+Enter   저장 후 다음
    0 ~ 6          Class 선택(선택 BBox 변경)   Ctrl+Z       되돌리기
    Delete         선택 BBox 삭제              F5           라벨 다시 불러오기
    + / - / F      Zoom In / Out / Fit         Esc          선택 해제
    ※ 한글 입력 상태에서는 알파벳 단축키가 안 먹을 수 있어요. (한/영 키로 영문 전환)
"""

import copy
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

# Pillow 9.1+ 는 Image.Resampling.BILINEAR, 예전 버전은 Image.BILINEAR → 둘 다 동작하게 처리
RESAMPLE = getattr(Image, "Resampling", Image)


# ==================================================
# 0. 설정값 (상수)
# ==================================================

APP_TITLE = "조각김치 이물검출 라벨링 프로그램 - Day 2"

# Class 목록 (리스트 순서 = YOLO class_id)
CLASS_NAMES = [
    "나뭇잎·종이류",          # 0
    "플라스틱류·돌·금속 등",   # 1
    "나뭇가지류",             # 2
    "벌레류",                 # 3
    "고무장갑",               # 4
    "병해·갈변",              # 5
    "파·고추",                # 6
]
CLASS_COLORS = ["#F59E0B", "#E91E63", "#16A34A", "#2563EB", "#9333EA", "#B45309", "#0891B2"]

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")

# ---------- 동작 관련 ----------
MIN_BOX_SIZE = 4      # 이보다 작게(화면 픽셀) 드래그하면 '클릭'으로 봅니다.
HANDLE_SIZE = 4       # 선택 BBox 모서리 핸들(□) 반지름
HANDLE_HIT = 7        # 핸들을 잡았다고 인정하는 거리
ZOOM_STEP = 1.25      # Zoom 한 번에 1.25배
MAX_SCALE = 20.0      # 최대 2000%
HISTORY_LIMIT = 50    # Ctrl+Z 되돌리기 최대 횟수

# ---------- 디자인 (교재 화면 느낌) ----------
FONT = "Malgun Gothic"     # 윈도우 기본 한글 폰트 (없으면 tkinter가 알아서 대체)
BG = "#EEF1F5"             # 창 배경
PANEL = "#FFFFFF"          # 패널 배경
BORDER = "#C9D1DC"
TEXT = "#1F2937"
MUTED = "#6B7280"
PRIMARY = "#1D6FE8"        # 파란 버튼 (새 BBox, 저장 후 다음)
PRIMARY_DARK = "#1557BD"
SUCCESS = "#16A34A"        # 초록 버튼 (저장)
SUCCESS_DARK = "#11823B"
DANGER = "#DC2626"         # 삭제
SELECT_BG = "#D6E6FF"      # 목록 선택 배경
CANVAS_BG = "#2B2F36"


# ==================================================
# 1. 순수 계산 함수들 (GUI와 무관 → 따로 테스트하기 쉬움)
# ==================================================

def bbox_to_yolo(x1, y1, x2, y2, img_w, img_h):
    """픽셀 좌표 (x1, y1, x2, y2) → YOLO (x_center, y_center, width, height), 모두 0~1"""
    x_center = (x1 + x2) / 2 / img_w
    y_center = (y1 + y2) / 2 / img_h
    width = (x2 - x1) / img_w
    height = (y2 - y1) / img_h
    return x_center, y_center, width, height


def yolo_to_bbox(x_center, y_center, width, height, img_w, img_h):
    """YOLO 좌표 → 픽셀 좌표 (bbox_to_yolo의 역방향)"""
    x1 = (x_center - width / 2) * img_w
    y1 = (y_center - height / 2) * img_h
    x2 = (x_center + width / 2) * img_w
    y2 = (y_center + height / 2) * img_h
    return x1, y1, x2, y2


def get_class_name(class_id):
    if 0 <= class_id < len(CLASS_NAMES):
        return CLASS_NAMES[class_id]
    return f"class{class_id}"          # 목록에 없는 번호가 와도 죽지 않게


def get_class_color(class_id):
    if 0 <= class_id < len(CLASS_COLORS):
        return CLASS_COLORS[class_id]
    return "#9CA3AF"


def get_label_path(image_path):
    """
    이미지 경로 → 라벨(TXT) 경로

    YOLO 규칙: 경로 안의 'images' 폴더를 'labels'로 바꾼 위치
        .../images/train/a.jpg  →  .../labels/train/a.txt
    경로에 'images'가 없으면 Day 1 방식
        .../my_images/a.jpg     →  .../my_images/labels/a.txt
    """
    p = Path(image_path)
    parts = list(p.parts)
    if "images" in parts[:-1]:
        idx = len(parts) - 1 - parts[::-1].index("images")   # 가장 마지막 'images'
        parts[idx] = "labels"
        return Path(*parts).with_suffix(".txt")
    return p.parent / "labels" / (p.stem + ".txt")


def collect_images(folder):
    """
    선택한 폴더에서 이미지 목록을 만듭니다.
    폴더 안에 images/ 가 있으면 그 아래(train, val ...)를 전부 뒤지고,
    없으면 선택한 폴더 바로 아래 이미지만 사용합니다.
    """
    folder = Path(folder)
    if (folder / "images").is_dir():
        root = folder / "images"
        candidates = root.rglob("*")           # 하위 폴더까지 전부
    else:
        root = folder
        candidates = root.iterdir()            # 현재 폴더만
    paths = sorted(p for p in candidates
                   if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS)
    return root, paths


def read_yolo_file(label_path, img_w, img_h):
    """
    YOLO TXT → BBox 목록. (원본 이미지 픽셀 좌표로 변환해서 돌려줍니다)
    잘못된 줄은 건너뛰고 줄 번호를 bad_lines 로 알려줍니다.
    """
    boxes, bad_lines = [], []
    if not os.path.exists(label_path):         # 아직 라벨이 없는 이미지
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


def write_yolo_file(label_path, boxes, img_w, img_h):
    """BBox 목록 → YOLO TXT. BBox가 0개면 빈 파일(= '객체 없음' 검수 완료)이 됩니다."""
    os.makedirs(os.path.dirname(label_path), exist_ok=True)
    with open(label_path, "w", encoding="utf-8") as f:
        for b in boxes:
            xc, yc, w, h = bbox_to_yolo(b["x1"], b["y1"], b["x2"], b["y2"], img_w, img_h)
            f.write(f"{b['cls']} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")


# ==================================================
# 2. 라벨링 프로그램 클래스
# ==================================================

class LabelingApp:
    """
    좌표계가 두 개라는 것만 기억하면 나머지는 쉽습니다.

        원본 이미지 좌표 : 저장/계산용. self.boxes 는 항상 이 좌표로 보관
        Canvas(화면) 좌표 : 마우스 이벤트, 그리기용

        Canvas = 원본 × scale + offset
        원본   = (Canvas − offset) ÷ scale

    Zoom 은 scale 을, Pan 은 offset 을 바꾸는 것뿐입니다.
    """

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1320x860")
        self.root.minsize(1100, 720)
        self.root.configure(bg=BG)

        # ---------- 폴더 / 이미지 ----------
        self.image_root = None       # 이미지 목록의 기준 폴더
        self.image_paths = []        # Path 목록
        self.index = 0
        self.pil_image = None        # 원본 PIL 이미지 (Zoom 할 때마다 여기서 잘라 씁니다)
        self.tk_image = None         # ⚠️ PhotoImage 참조를 붙잡아 둬야 화면에서 안 사라짐
        self.img_w = 0
        self.img_h = 0

        # ---------- 보기 (Zoom / Pan) ----------
        self.scale = 1.0
        self.off_x = 0.0
        self.off_y = 0.0
        self.fit_mode = True         # True면 창 크기가 바뀔 때 자동으로 다시 맞춤

        # ---------- 라벨 ----------
        # BBox 하나 = {"cls": 1, "x1": .., "y1": .., "x2": .., "y2": ..}  (원본 픽셀 좌표)
        self.boxes = []
        self.selected = None         # 선택된 BBox 번호 (없으면 None)
        self.history = []            # 되돌리기용 스냅샷
        self.dirty = False           # 저장 안 된 변경이 있는지
        self.current_class = 0

        # ---------- 마우스 ----------
        self.mode = "draw"           # "draw"(새 BBox) / "select"(선택 이동) / "pan"
        self.drag = None             # 지금 진행 중인 드래그 정보 (dict)

        self.mode_var = tk.StringVar(value="draw")
        self.auto_save_var = tk.BooleanVar(value=False)

        self.setup_style()
        self.build_menu()
        self.build_ui()
        self.bind_events()
        self.set_mode("draw")
        self.set_current_class(0, apply_to_selected=False)
        self.render()

    # ==================================================
    # 2-1. 화면 구성
    # ==================================================

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")      # 윈도우 기본 테마보다 색 지정이 잘 먹습니다.
        except tk.TclError:
            pass
        style.configure("TCombobox", padding=4)
        self.root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    def build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="폴더 열기...", accelerator="Ctrl+O", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="저장", accelerator="Ctrl+S", command=self.save_labels)
        file_menu.add_command(label="저장 후 다음", accelerator="Ctrl+Enter", command=self.save_and_next)
        file_menu.add_command(label="라벨 다시 불러오기", accelerator="F5", command=self.reload_labels)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.on_close)
        menubar.add_cascade(label="파일(F)", menu=file_menu, underline=3)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Zoom In", accelerator="+", command=self.zoom_in)
        view_menu.add_command(label="Zoom Out", accelerator="-", command=self.zoom_out)
        view_menu.add_command(label="화면에 맞춤 (Fit)", accelerator="F", command=self.fit_to_window)
        view_menu.add_separator()
        view_menu.add_radiobutton(label="Pan 모드", accelerator="H", value="pan",
                                  variable=self.mode_var, command=lambda: self.set_mode("pan"))
        menubar.add_cascade(label="보기(V)", menu=view_menu, underline=3)

        tool_menu = tk.Menu(menubar, tearoff=0)
        tool_menu.add_radiobutton(label="새 BBox 그리기", accelerator="W", value="draw",
                                  variable=self.mode_var, command=lambda: self.set_mode("draw"))
        tool_menu.add_radiobutton(label="선택 이동", accelerator="E", value="select",
                                  variable=self.mode_var, command=lambda: self.set_mode("select"))
        tool_menu.add_separator()
        tool_menu.add_command(label="선택 BBox 삭제", accelerator="Delete", command=self.delete_selected)
        tool_menu.add_command(label="되돌리기", accelerator="Ctrl+Z", command=self.undo)
        tool_menu.add_separator()
        tool_menu.add_checkbutton(label="이미지 이동 시 자동 저장", variable=self.auto_save_var)
        menubar.add_cascade(label="도구(T)", menu=tool_menu, underline=3)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="단축키 안내", command=self.show_shortcuts)
        help_menu.add_command(label="프로그램 정보", command=lambda: messagebox.showinfo(
            "정보", f"{APP_TITLE}\n\n교재 7 · 2일차 라벨링 프로그램 핵심 기능"))
        menubar.add_cascade(label="도움말(H)", menu=help_menu, underline=4)

        self.root.config(menu=menubar)

    def make_group(self, parent, title):
        """제목이 있는 흰색 박스 (교재 화면의 '보기 도구', 'Class 선택' 같은 영역)"""
        return tk.LabelFrame(parent, text=f" {title} ", font=(FONT, 10, "bold"),
                             bg=PANEL, fg=TEXT, bd=1, relief="solid",
                             padx=8, pady=6, labelanchor="nw")

    def tool_button(self, parent, icon, text, command, width=9,
                    bg=PANEL, fg=TEXT, active_bg=SELECT_BG):
        """아이콘(위) + 글자(아래) 모양의 툴바 버튼"""
        btn = tk.Button(parent, text=f"{icon}\n{text}", command=command, width=width,
                        font=(FONT, 9), bg=bg, fg=fg, activebackground=active_bg,
                        activeforeground=fg, relief="solid", bd=1, cursor="hand2",
                        padx=4, pady=3)
        btn.pack(side="left", padx=3)
        btn.default_colors = (bg, fg)      # 모드 버튼 강조 후 원래 색으로 돌리기 위해 기억
        return btn

    def build_ui(self):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        main = tk.Frame(self.root, bg=BG)
        main.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        main.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)       # 가운데(이미지)만 창 크기에 따라 늘어남

        self.build_left_panel(main)
        self.build_center_panel(main)
        self.build_right_panel(main)
        self.build_toolbar()

        # ---------- 맨 아래 상태 표시줄 ----------
        self.status_label = tk.Label(self.root, text="파일 > 폴더 열기 (Ctrl+O)로 시작하세요.",
                                     anchor="w", bg="#E2E7EE", fg=TEXT, font=(FONT, 9),
                                     padx=10, pady=3)
        self.status_label.grid(row=2, column=0, sticky="ew")

    # ---------- ① 왼쪽: 이미지 목록 ----------
    def build_left_panel(self, parent):
        self.left_group = self.make_group(parent, "이미지 목록 (0)")
        self.left_group.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        tk.Button(self.left_group, text="폴더 열기…", command=self.open_folder,
                  font=(FONT, 9), bg=PANEL, relief="solid", bd=1,
                  cursor="hand2", activebackground=SELECT_BG).pack(fill="x", pady=(0, 6))

        wrap = tk.Frame(self.left_group, bg=PANEL)
        wrap.pack(fill="both", expand=True)

        # exportselection=False: 다른 Listbox를 클릭해도 이 목록의 선택이 풀리지 않게!
        self.image_list = tk.Listbox(wrap, width=28, exportselection=False,
                                     font=(FONT, 9), activestyle="none",
                                     selectbackground=SELECT_BG, selectforeground=PRIMARY_DARK,
                                     bd=1, relief="solid", highlightthickness=0)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.image_list.yview)
        self.image_list.config(yscrollcommand=scroll.set)
        self.image_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.progress_label = tk.Label(self.left_group, text="라벨 TXT 있음 0 / 0",
                                       font=(FONT, 9), bg=PANEL, fg=MUTED, anchor="w")
        self.progress_label.pack(fill="x", pady=(6, 0))

    # ---------- ② 가운데: 파일명 + 이미지 Canvas ----------
    def build_center_panel(self, parent):
        center = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        center.grid(row=0, column=1, sticky="nsew")

        header = tk.Frame(center, bg=PANEL)
        header.pack(fill="x", padx=10, pady=6)
        self.name_label = tk.Label(header, text="(폴더를 열어주세요)",
                                   font=(FONT, 11, "bold"), bg=PANEL, fg=TEXT)
        self.name_label.pack(side="left")
        self.count_label = tk.Label(header, text="", font=(FONT, 11, "bold"), bg=PANEL, fg=TEXT)
        self.count_label.pack(side="left", padx=18)
        self.zoom_label = tk.Label(header, text="", font=(FONT, 9), bg=PANEL, fg=MUTED)
        self.zoom_label.pack(side="right")

        self.canvas = tk.Canvas(center, bg=CANVAS_BG, highlightthickness=0,
                                width=820, height=520)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ---------- ③ 오른쪽: Class 선택 / 선택된 BBox 정보 / BBox 목록 ----------
    def build_right_panel(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.grid(row=0, column=2, sticky="ns", padx=(8, 0))

        # --- Class 선택 ---
        cls_group = self.make_group(right, "Class 선택")
        cls_group.pack(fill="x")

        self.class_combo = ttk.Combobox(cls_group, state="readonly", width=26, font=(FONT, 10),
                                        values=[f"{i}. {n}" for i, n in enumerate(CLASS_NAMES)])
        self.class_combo.pack(fill="x", pady=(0, 6))

        self.class_list = tk.Listbox(cls_group, height=len(CLASS_NAMES), exportselection=False,
                                     font=(FONT, 10), activestyle="none",
                                     selectbackground=PRIMARY, selectforeground="white",
                                     bd=1, relief="solid", highlightthickness=0)
        for i, name in enumerate(CLASS_NAMES):
            self.class_list.insert("end", f" ■  {i}.  {name}")
            self.class_list.itemconfig(i, foreground=get_class_color(i))
        self.class_list.pack(fill="x")

        tk.Label(cls_group, text="새 BBox의 Class / 선택한 BBox의 Class 변경",
                 font=(FONT, 8), bg=PANEL, fg=MUTED).pack(anchor="w", pady=(4, 0))

        # --- 현재 선택된 BBox 정보 ---
        info = self.make_group(right, "현재 선택된 BBox 정보")
        info.pack(fill="x", pady=(10, 0))

        self.info_vars = {}
        self.info_entries = []
        rows = [("Class", "cls"), ("X(중심)", "xc"), ("Y(중심)", "yc"),
                ("너비", "w"), ("높이", "h")]
        for r, (title, key) in enumerate(rows):
            tk.Label(info, text=title, font=(FONT, 9), bg=PANEL, fg=TEXT,
                     width=8, anchor="w").grid(row=r, column=0, sticky="w", pady=2)
            var = tk.StringVar()
            entry = tk.Entry(info, textvariable=var, width=16, font=(FONT, 10),
                             relief="solid", bd=1)
            entry.grid(row=r, column=1, sticky="ew", pady=2)
            entry.bind("<Return>", lambda e: self.apply_info())     # Enter = 적용
            self.info_vars[key] = var
            self.info_entries.append(entry)

        self.info_class_name = tk.Label(info, text="선택된 BBox 없음", font=(FONT, 8),
                                        bg=PANEL, fg=MUTED, anchor="w")
        self.info_class_name.grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 4))

        tk.Button(info, text="적용 (Enter)", command=self.apply_info, font=(FONT, 9),
                  bg=PANEL, relief="solid", bd=1, cursor="hand2",
                  activebackground=SELECT_BG).grid(row=6, column=0, columnspan=2, sticky="ew")

        # --- 이 이미지의 BBox 목록 (겹친 BBox를 고르기 편하게) ---
        self.box_group = self.make_group(right, "이 이미지의 BBox (0)")
        self.box_group.pack(fill="both", expand=True, pady=(10, 0))
        wrap = tk.Frame(self.box_group, bg=PANEL)
        wrap.pack(fill="both", expand=True)
        self.box_list = tk.Listbox(wrap, height=6, exportselection=False, font=(FONT, 9),
                                   activestyle="none", selectbackground=SELECT_BG,
                                   selectforeground=TEXT, bd=1, relief="solid",
                                   highlightthickness=0)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.box_list.yview)
        self.box_list.config(yscrollcommand=scroll.set)
        self.box_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # ---------- ④ 아래: 보기 도구 / 라벨 도구 / 이미지 이동 및 저장 ----------
    def build_toolbar(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(4, 8))

        view = self.make_group(bar, "보기 도구")
        view.pack(side="left")
        self.tool_button(view, "⊕", "Zoom In", self.zoom_in, width=7)
        self.tool_button(view, "⊖", "Zoom Out", self.zoom_out, width=7)
        self.tool_button(view, "⛶", "Fit", self.fit_to_window, width=7)
        pan_btn = self.tool_button(view, "✋", "Pan", lambda: self.set_mode("pan"), width=7)

        label = self.make_group(bar, "라벨 도구")
        label.pack(side="left", padx=12)
        draw_btn = self.tool_button(label, "＋", "새 BBox 그리기", lambda: self.set_mode("draw"), width=13)
        select_btn = self.tool_button(label, "➤", "선택 이동", lambda: self.set_mode("select"), width=11)
        self.tool_button(label, "✕", "삭제", self.delete_selected, width=8, fg=DANGER)

        # 모드 버튼은 지금 모드일 때 파란색으로 칠해 줍니다.
        self.mode_buttons = {"draw": draw_btn, "select": select_btn, "pan": pan_btn}

        nav = self.make_group(bar, "이미지 이동 및 저장")
        nav.pack(side="right")
        self.tool_button(nav, "◀", "이전 (A)", self.prev_image, width=8)
        self.tool_button(nav, "▶", "다음 (D)", self.next_image, width=8)
        self.tool_button(nav, "✔", "저장 (Ctrl+S)", self.save_labels, width=12,
                         bg=SUCCESS, fg="white", active_bg=SUCCESS_DARK)
        self.tool_button(nav, "⏭", "저장 후 다음", self.save_and_next, width=12,
                         bg=PRIMARY, fg="white", active_bg=PRIMARY_DARK)

    # ==================================================
    # 2-2. 이벤트 연결
    # ==================================================

    def bind_events(self):
        c = self.canvas
        # 왼쪽 버튼: 모드에 따라 그리기 / 선택·이동·크기조절 / Pan
        c.bind("<ButtonPress-1>", self.on_left_down)
        c.bind("<B1-Motion>", self.on_left_drag)
        c.bind("<ButtonRelease-1>", self.on_left_up)
        c.bind("<Motion>", self.on_mouse_move)
        # 오른쪽·가운데 버튼 드래그: 언제든 Pan
        for n in (2, 3):
            c.bind(f"<ButtonPress-{n}>", self.on_pan_down)
            c.bind(f"<B{n}-Motion>", self.on_pan_drag)
            c.bind(f"<ButtonRelease-{n}>", self.on_pan_up)
        # 마우스 휠: Windows/Mac 은 <MouseWheel>, 리눅스는 Button-4/5
        c.bind("<MouseWheel>", self.on_wheel)
        c.bind("<Button-4>", self.on_wheel)
        c.bind("<Button-5>", self.on_wheel)
        # 창 크기가 바뀌면 다시 그리기
        c.bind("<Configure>", self.on_canvas_resize)

        self.image_list.bind("<<ListboxSelect>>", self.on_image_list_select)
        self.class_combo.bind("<<ComboboxSelected>>", self.on_class_combo_select)
        self.class_list.bind("<<ListboxSelect>>", self.on_class_list_select)
        self.box_list.bind("<<ListboxSelect>>", self.on_box_list_select)

        # ---------- 단축키 ----------
        self.bind_key("<Control-o>", self.open_folder, allow_in_entry=True)
        self.bind_key("<Control-s>", self.save_labels, allow_in_entry=True)
        self.bind_key("<Control-Return>", self.save_and_next, allow_in_entry=True)
        self.bind_key("<Control-z>", self.undo)
        self.bind_key("<F5>", self.reload_labels, allow_in_entry=True)
        for key, func in [("a", self.prev_image), ("d", self.next_image),
                          ("w", lambda: self.set_mode("draw")),
                          ("e", lambda: self.set_mode("select")),
                          ("h", lambda: self.set_mode("pan")),
                          ("f", self.fit_to_window)]:
            self.bind_key(f"<{key}>", func)
            self.bind_key(f"<{key.upper()}>", func)           # CapsLock 켜져 있어도 동작
        for seq in ("<plus>", "<equal>", "<KP_Add>"):
            self.bind_key(seq, self.zoom_in)
        for seq in ("<minus>", "<KP_Subtract>"):
            self.bind_key(seq, self.zoom_out)
        self.bind_key("<Delete>", self.delete_selected)
        self.bind_key("<BackSpace>", self.delete_selected)
        self.bind_key("<Escape>", self.on_escape)
        # 숫자키 0~9 → Class 선택. "<1>"은 마우스 버튼이라서 꼭 "<Key-1>"로 써야 합니다!
        for i in range(min(10, len(CLASS_NAMES))):
            self.bind_key(f"<Key-{i}>", lambda i=i: self.set_current_class(i))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def bind_key(self, sequence, func, allow_in_entry=False):
        """
        root 전체에 단축키를 겁니다.
        단, 오른쪽 입력칸(Entry)에 숫자를 치는 중에 'd'나 Delete 가
        '다음 이미지', 'BBox 삭제'로 동작하면 곤란하니 입력 중엔 무시합니다.
        """
        def handler(event):
            if not allow_in_entry and self.is_typing():
                return None                  # Entry가 원래대로 글자를 받도록 양보
            func()
            return "break"                   # 다른 위젯으로 이벤트가 더 퍼지지 않게
        self.root.bind(sequence, handler)

    def is_typing(self):
        try:
            widget = self.root.focus_get()
        except (KeyError, tk.TclError):
            return False
        return isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Spinbox))

    # ==================================================
    # 2-3. 폴더 열기 & 이미지 로드
    # ==================================================

    def open_folder(self):
        if not self.confirm_leave():
            return
        folder = filedialog.askdirectory(title="프로젝트 데이터 폴더 또는 이미지 폴더 선택")
        if folder:                            # 취소하면 빈 문자열
            self.load_folder(folder)

    def load_folder(self, folder):
        image_root, paths = collect_images(folder)
        if not paths:
            messagebox.showwarning("이미지 없음", "선택한 폴더에 이미지 파일이 없습니다.")
            return

        self.image_root = image_root
        self.image_paths = paths
        self.index = 0
        self.dirty = False

        # 하위 폴더(train/val)가 여러 개면 'train/xxx.jpg'처럼, 아니면 파일명만 표시
        multi_dirs = len({p.parent for p in paths}) > 1
        self.image_list.delete(0, "end")
        for i, p in enumerate(paths):
            name = p.relative_to(image_root).as_posix() if multi_dirs else p.name
            self.image_list.insert("end", f"  {name}")
            self.update_list_item_color(i)

        self.left_group.config(text=f" 이미지 목록 ({len(paths)}) ")
        self.update_progress()
        self.load_image()

    def update_list_item_color(self, i):
        """라벨 TXT가 아직 없는 이미지는 회색으로 → 남은 작업이 한눈에 보입니다."""
        has_label = get_label_path(self.image_paths[i]).exists()
        self.image_list.itemconfig(i, foreground=TEXT if has_label else "#A0A7B2")

    def update_progress(self):
        done = sum(get_label_path(p).exists() for p in self.image_paths)
        self.progress_label.config(text=f"라벨 TXT 있음 {done} / {len(self.image_paths)}")

    def load_image(self):
        path = self.image_paths[self.index]
        try:
            with Image.open(path) as im:
                self.pil_image = im.convert("RGB")
        except OSError as e:
            messagebox.showerror("이미지 열기 실패", f"{path.name}\n\n{e}")
            return
        self.img_w, self.img_h = self.pil_image.size

        # 같은 이름의 TXT 자동 로드
        label_path = get_label_path(path)
        self.boxes, bad_lines = read_yolo_file(label_path, self.img_w, self.img_h)
        self.selected = None
        self.history = []
        self.dirty = False
        self.drag = None

        self.fit_to_window()
        self.refresh_boxes()
        self.sync_image_list()

        msg = (f"{path.name} 열기  |  원본 {self.img_w}x{self.img_h}  |  "
               f"기존 BBox {len(self.boxes)}개"
               + ("" if label_path.exists() else "  (라벨 TXT 없음 → 새로 작성)"))
        if bad_lines:
            msg += f"  |  ⚠ 형식 오류 줄 {bad_lines} 건너뜀"
        self.set_status(msg)

    def sync_image_list(self):
        self.image_list.selection_clear(0, "end")
        if self.image_paths:
            self.image_list.selection_set(self.index)
            self.image_list.see(self.index)

    # ==================================================
    # 2-4. 좌표 변환 & 화면 그리기 (Zoom / Pan 대응)
    # ==================================================

    def canvas_to_image(self, cx, cy):
        return (cx - self.off_x) / self.scale, (cy - self.off_y) / self.scale

    def image_to_canvas(self, ix, iy):
        return ix * self.scale + self.off_x, iy * self.scale + self.off_y

    def clamp_image_xy(self, ix, iy):
        """원본 좌표를 이미지 안쪽(0 ~ w, 0 ~ h)으로 붙잡아 둡니다."""
        return min(max(ix, 0.0), float(self.img_w)), min(max(iy, 0.0), float(self.img_h))

    def canvas_size(self):
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w <= 1:                            # 창이 아직 화면에 안 그려졌을 때
            w, h = int(self.canvas["width"]), int(self.canvas["height"])
        return w, h

    def render(self):
        """이미지 + BBox 를 처음부터 다시 그립니다. (Zoom / Pan / 이미지 변경 시)"""
        self.canvas.delete("all")
        cw, ch = self.canvas_size()

        if self.pil_image is None:
            self.canvas.create_text(cw / 2, ch / 2, fill="#9CA3AF", font=(FONT, 13),
                                    text="파일 > 폴더 열기 (Ctrl+O)\n\n프로젝트 데이터 폴더를 선택하세요.",
                                    justify="center")
            return

        # 핵심 아이디어: 전체 이미지를 확대하지 않고 '화면에 보이는 부분만' 잘라서 확대
        # → 2000% 로 확대해도 메모리/속도 문제가 없습니다.
        s = self.scale
        x0, y0 = self.clamp_image_xy(*self.canvas_to_image(0, 0))
        x1, y1 = self.clamp_image_xy(*self.canvas_to_image(cw, ch))
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
            px, py = self.image_to_canvas(left, top)
            self.canvas.create_image(px, py, anchor="nw", image=self.tk_image, tags="image")

        self.draw_boxes()
        self.zoom_label.config(text=f"Zoom {self.scale * 100:.0f}%")

    def draw_boxes(self):
        """BBox 만 다시 그립니다. (드래그 중에는 이미지까지 다시 그리면 느려서 분리)"""
        self.canvas.delete("box")
        order = [i for i in range(len(self.boxes)) if i != self.selected]
        if self.selected is not None:
            order.append(self.selected)          # 선택된 BBox를 맨 위에

        for i in order:
            b = self.boxes[i]
            color = get_class_color(b["cls"])
            is_sel = (i == self.selected)
            cx1, cy1 = self.image_to_canvas(b["x1"], b["y1"])
            cx2, cy2 = self.image_to_canvas(b["x2"], b["y2"])

            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=color,
                                         width=3 if is_sel else 2, tags="box")

            # 교재처럼 '2 나뭇가지류' 색깔 태그. 위쪽 공간이 없으면 박스 안쪽에 붙입니다.
            text = f"{b['cls']} {get_class_name(b['cls'])}"
            if cy1 - 20 >= 0:
                tid = self.canvas.create_text(cx1 + 5, cy1 - 3, anchor="sw", text=text,
                                              fill="white", font=(FONT, 10, "bold"), tags="box")
            else:
                tid = self.canvas.create_text(cx1 + 5, cy1 + 3, anchor="nw", text=text,
                                              fill="white", font=(FONT, 10, "bold"), tags="box")
            tx1, ty1, tx2, ty2 = self.canvas.bbox(tid)
            bg_id = self.canvas.create_rectangle(tx1 - 5, ty1 - 1, tx2 + 5, ty2 + 1,
                                                 fill=color, outline=color, tags="box")
            self.canvas.tag_raise(tid, bg_id)

            if is_sel:                           # 크기 조절용 핸들 8개
                for hx, hy in self.handle_positions(b).values():
                    self.canvas.create_rectangle(hx - HANDLE_SIZE, hy - HANDLE_SIZE,
                                                 hx + HANDLE_SIZE, hy + HANDLE_SIZE,
                                                 fill="white", outline=color, width=2, tags="box")

    def handle_positions(self, b):
        """선택 BBox의 핸들 위치 (Canvas 좌표). 이름의 n/s/e/w = 북/남/동/서"""
        x1, y1 = self.image_to_canvas(b["x1"], b["y1"])
        x2, y2 = self.image_to_canvas(b["x2"], b["y2"])
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        return {"nw": (x1, y1), "n": (mx, y1), "ne": (x2, y1), "e": (x2, my),
                "se": (x2, y2), "s": (mx, y2), "sw": (x1, y2), "w": (x1, my)}

    def refresh_boxes(self):
        """BBox 가 바뀌었을 때 관련된 화면을 한꺼번에 갱신"""
        self.draw_boxes()
        self.update_info_panel()
        self.update_box_list()
        self.update_header()

    def update_header(self):
        if not self.image_paths:
            return
        star = "  ● 저장 안 됨" if self.dirty else ""
        self.name_label.config(text=self.image_paths[self.index].name + star,
                               fg=DANGER if self.dirty else TEXT)
        self.count_label.config(text=f"( {self.index + 1} / {len(self.image_paths)} )")

    def set_status(self, text):
        self.status_label.config(text=text)

    # ==================================================
    # 2-5. 마우스: 새 BBox / 선택 · 이동 · 크기 조절
    # ==================================================

    def hit_handle(self, x, y):
        if self.selected is None:
            return None
        for name, (hx, hy) in self.handle_positions(self.boxes[self.selected]).items():
            if abs(x - hx) <= HANDLE_HIT and abs(y - hy) <= HANDLE_HIT:
                return name
        return None

    def hit_box(self, x, y):
        """클릭 위치를 포함하는 BBox 중 '가장 작은 것'을 고릅니다. (큰 박스 안의 작은 박스 선택용)"""
        best, best_area = None, None
        for i, b in enumerate(self.boxes):
            x1, y1 = self.image_to_canvas(b["x1"], b["y1"])
            x2, y2 = self.image_to_canvas(b["x2"], b["y2"])
            if x1 - 3 <= x <= x2 + 3 and y1 - 3 <= y <= y2 + 3:
                area = (x2 - x1) * (y2 - y1)
                if best is None or area < best_area:
                    best, best_area = i, area
        return best

    def on_left_down(self, event):
        self.canvas.focus_set()               # 입력칸 포커스를 빼서 단축키가 먹게
        if self.pil_image is None:
            return

        if self.mode == "pan":
            self.start_pan(event)
            return

        if self.mode == "select":
            handle = self.hit_handle(event.x, event.y)
            if handle:                                        # ① 핸들 → 크기 조절
                b = self.boxes[self.selected]
                self.drag = {"type": "resize", "handle": handle,
                             "orig": dict(b), "snapshot": copy.deepcopy(self.boxes)}
                return
            idx = self.hit_box(event.x, event.y)
            if idx is not None:                               # ② 박스 안 → 선택 + 이동
                self.select_box(idx)
                ix, iy = self.canvas_to_image(event.x, event.y)
                self.drag = {"type": "move", "ix": ix, "iy": iy,
                             "orig": dict(self.boxes[idx]),
                             "snapshot": copy.deepcopy(self.boxes)}
            else:                                             # ③ 빈 곳 → 선택 해제
                self.select_box(None)
            return

        # mode == "draw": 이미지 안쪽에서만 시작
        ix, iy = self.clamp_image_xy(*self.canvas_to_image(event.x, event.y))
        sx, sy = self.image_to_canvas(ix, iy)
        color = get_class_color(self.current_class)
        rect = self.canvas.create_rectangle(sx, sy, sx, sy, outline=color, width=2,
                                            dash=(4, 2), tags="temp")
        self.drag = {"type": "draw", "ix": ix, "iy": iy, "rect": rect}

    def on_left_drag(self, event):
        d = self.drag
        if d is None:
            return
        if d["type"] == "pan":
            self.do_pan(event)
            return

        ix, iy = self.clamp_image_xy(*self.canvas_to_image(event.x, event.y))

        if d["type"] == "draw":
            sx, sy = self.image_to_canvas(d["ix"], d["iy"])
            ex, ey = self.image_to_canvas(ix, iy)
            self.canvas.coords(d["rect"], sx, sy, ex, ey)

        elif d["type"] == "move":
            o = d["orig"]
            w, h = o["x2"] - o["x1"], o["y2"] - o["y1"]
            # 이동량만큼 옮기되, 박스 전체가 이미지 밖으로 나가지 않게
            nx1 = min(max(o["x1"] + (ix - d["ix"]), 0.0), self.img_w - w)
            ny1 = min(max(o["y1"] + (iy - d["iy"]), 0.0), self.img_h - h)
            b = self.boxes[self.selected]
            b.update(x1=nx1, y1=ny1, x2=nx1 + w, y2=ny1 + h)
            self.draw_boxes()
            self.update_info_panel()

        elif d["type"] == "resize":
            b = self.boxes[self.selected]
            h = d["handle"]
            if "w" in h: b["x1"] = ix
            if "e" in h: b["x2"] = ix
            if "n" in h: b["y1"] = iy
            if "s" in h: b["y2"] = iy
            self.draw_boxes()
            self.update_info_panel()

    def on_left_up(self, event):
        d, self.drag = self.drag, None
        if d is None:
            return
        if d["type"] == "pan":
            self.end_pan()
            return

        if d["type"] == "draw":
            self.canvas.delete(d["rect"])
            ix, iy = self.clamp_image_xy(*self.canvas_to_image(event.x, event.y))
            x1, x2 = sorted((d["ix"], ix))      # 어느 방향으로 드래그해도 (왼쪽위, 오른쪽아래)
            y1, y2 = sorted((d["iy"], iy))

            # 너무 작으면 '클릭'으로 보고 → 그 자리 BBox 선택 (모드 전환 없이 빠르게 고르기)
            if (x2 - x1) * self.scale < MIN_BOX_SIZE or (y2 - y1) * self.scale < MIN_BOX_SIZE:
                idx = self.hit_box(event.x, event.y)
                self.select_box(idx)
                if idx is None:
                    self.set_status("BBox가 너무 작아서 무시했습니다.")
                return

            self.push_history()
            self.boxes.append({"cls": self.current_class, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
            self.mark_dirty()
            self.select_box(len(self.boxes) - 1)
            self.set_status(f"[{self.current_class} {get_class_name(self.current_class)}] "
                            f"BBox 추가 ({x1:.0f}, {y1:.0f}) ~ ({x2:.0f}, {y2:.0f})  |  "
                            f"BBox {len(self.boxes)}개")
            return

        # move / resize 마무리
        b = self.boxes[self.selected]
        b["x1"], b["x2"] = sorted((b["x1"], b["x2"]))     # 핸들을 반대편으로 넘긴 경우 정리
        b["y1"], b["y2"] = sorted((b["y1"], b["y2"]))
        if b["x2"] - b["x1"] < 1:
            b["x2"] = min(float(self.img_w), b["x1"] + 1)
        if b["y2"] - b["y1"] < 1:
            b["y2"] = min(float(self.img_h), b["y1"] + 1)

        if b != d["orig"]:                                  # 실제로 바뀐 경우만 기록
            self.history.append(d["snapshot"])
            del self.history[:-HISTORY_LIMIT]
            self.mark_dirty()
            self.set_status("BBox 이동 완료" if d["type"] == "move" else "BBox 크기 조절 완료")
        self.refresh_boxes()

    def on_mouse_move(self, event):
        """선택 이동 모드에서 핸들/박스 위에 올리면 커서 모양을 바꿔 힌트를 줍니다."""
        if self.mode != "select" or self.drag is not None or self.pil_image is None:
            return
        handle = self.hit_handle(event.x, event.y)
        cursors = {"nw": "top_left_corner", "se": "bottom_right_corner",
                   "ne": "top_right_corner", "sw": "bottom_left_corner",
                   "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                   "e": "sb_h_double_arrow", "w": "sb_h_double_arrow"}
        if handle:
            cursor = cursors[handle]
        elif self.hit_box(event.x, event.y) is not None:
            cursor = "fleur"
        else:
            cursor = "arrow"
        self.canvas.config(cursor=cursor)

    # ==================================================
    # 2-6. Zoom / Pan
    # ==================================================

    def fit_scale(self):
        cw, ch = self.canvas_size()
        return min(cw / self.img_w, ch / self.img_h)

    def fit_to_window(self):
        if self.pil_image is None:
            return
        cw, ch = self.canvas_size()
        self.scale = self.fit_scale()
        self.off_x = (cw - self.img_w * self.scale) / 2     # 가운데 정렬
        self.off_y = (ch - self.img_h * self.scale) / 2
        self.fit_mode = True
        self.render()

    def zoom_at(self, factor, cx, cy):
        """
        (cx, cy) 지점을 고정한 채로 확대/축소합니다.
        마우스 아래의 원본 좌표가 Zoom 전후로 같은 화면 위치에 있도록 offset 을 다시 계산합니다.
        """
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
        cw, ch = self.canvas_size()
        self.zoom_at(ZOOM_STEP, cw / 2, ch / 2)

    def zoom_out(self):
        cw, ch = self.canvas_size()
        self.zoom_at(1 / ZOOM_STEP, cw / 2, ch / 2)

    def on_wheel(self, event):
        up = event.delta > 0 if event.num not in (4, 5) else event.num == 4
        self.zoom_at(ZOOM_STEP if up else 1 / ZOOM_STEP, event.x, event.y)

    def start_pan(self, event):
        self.drag = {"type": "pan", "x": event.x, "y": event.y}
        self.canvas.config(cursor="fleur")

    def do_pan(self, event):
        # 드래그 중에는 이미 그려진 것을 통째로 '옮기기'만 → 빠름
        d = self.drag
        dx, dy = event.x - d["x"], event.y - d["y"]
        self.canvas.move("all", dx, dy)
        self.off_x += dx
        self.off_y += dy
        d["x"], d["y"] = event.x, event.y

    def end_pan(self):
        self.fit_mode = False
        self.set_mode(self.mode)               # 커서 원래대로
        self.render()                          # 놓았을 때 새로 보이는 영역까지 다시 그리기

    def on_pan_down(self, event):
        if self.pil_image is not None and self.drag is None:
            self.start_pan(event)

    def on_pan_drag(self, event):
        if self.drag and self.drag["type"] == "pan":
            self.do_pan(event)

    def on_pan_up(self, event):
        if self.drag and self.drag["type"] == "pan":
            self.drag = None
            self.end_pan()

    def on_canvas_resize(self, event):
        if self.pil_image is not None and self.fit_mode:
            self.fit_to_window()
        else:
            self.render()

    # ==================================================
    # 2-7. 모드 / 선택 / Class / 정보 패널
    # ==================================================

    def set_mode(self, mode):
        self.mode = mode
        self.mode_var.set(mode)
        for m, btn in self.mode_buttons.items():
            bg, fg = btn.default_colors
            if m == mode:
                btn.config(bg=PRIMARY, fg="white", activebackground=PRIMARY_DARK,
                           activeforeground="white")
            else:
                btn.config(bg=bg, fg=fg, activebackground=SELECT_BG, activeforeground=fg)
        self.canvas.config(cursor={"draw": "crosshair", "select": "arrow", "pan": "fleur"}[mode])
        names = {"draw": "새 BBox 그리기 (드래그)", "select": "선택 이동 (클릭 선택 · 드래그 이동 · 핸들로 크기 조절)",
                 "pan": "Pan (드래그로 화면 이동)"}
        self.set_status(f"모드: {names[mode]}")

    def select_box(self, idx):
        self.selected = idx
        if idx is not None:
            # 선택한 BBox의 Class 를 오른쪽 Class 선택칸에도 보여줍니다. (변경 X, 표시만)
            self.set_current_class(self.boxes[idx]["cls"], apply_to_selected=False, quiet=True)
        self.refresh_boxes()

    def set_current_class(self, class_id, apply_to_selected=True, quiet=False):
        if not (0 <= class_id < len(CLASS_NAMES)):
            return
        self.current_class = class_id
        # Combobox / Listbox 둘 다 맞춰줍니다. (코드로 바꾸면 Select 이벤트는 안 생겨서 무한루프 X)
        self.class_combo.current(class_id)
        self.class_list.selection_clear(0, "end")
        self.class_list.selection_set(class_id)
        self.class_list.see(class_id)

        if apply_to_selected and self.selected is not None:
            box = self.boxes[self.selected]
            if box["cls"] != class_id:
                old = box["cls"]
                self.push_history()
                box["cls"] = class_id
                self.mark_dirty()
                self.refresh_boxes()
                self.set_status(f"Class 변경: {old} {get_class_name(old)} → "
                                f"{class_id} {get_class_name(class_id)}")
                return
        if not quiet:
            self.set_status(f"현재 Class: {class_id} {get_class_name(class_id)}")

    def on_class_combo_select(self, event):
        self.set_current_class(self.class_combo.current())
        self.canvas.focus_set()                # 콤보박스 포커스 해제 → 단축키 계속 사용

    def on_class_list_select(self, event):
        sel = self.class_list.curselection()
        if sel:
            self.set_current_class(sel[0])

    def on_box_list_select(self, event):
        sel = self.box_list.curselection()
        if sel:
            self.select_box(sel[0])

    def on_escape(self):
        if self.drag and self.drag["type"] == "draw":
            self.canvas.delete(self.drag["rect"])
            self.drag = None
            self.set_status("그리기 취소")
        else:
            self.select_box(None)

    def update_info_panel(self):
        if self.selected is None:
            for var in self.info_vars.values():
                var.set("")
            self.info_class_name.config(text="선택된 BBox 없음", fg=MUTED)
            return
        b = self.boxes[self.selected]
        xc, yc, w, h = bbox_to_yolo(b["x1"], b["y1"], b["x2"], b["y2"], self.img_w, self.img_h)
        self.info_vars["cls"].set(str(b["cls"]))
        self.info_vars["xc"].set(f"{xc:.4f}")
        self.info_vars["yc"].set(f"{yc:.4f}")
        self.info_vars["w"].set(f"{w:.4f}")
        self.info_vars["h"].set(f"{h:.4f}")
        self.info_class_name.config(
            text=f"#{self.selected + 1}  {get_class_name(b['cls'])}  |  "
                 f"{b['x2'] - b['x1']:.0f} x {b['y2'] - b['y1']:.0f} px",
            fg=get_class_color(b["cls"]))

    def apply_info(self):
        """오른쪽 입력칸에서 직접 고친 Class / YOLO 좌표를 BBox 에 반영"""
        if self.selected is None:
            self.set_status("먼저 BBox를 선택하세요.")
            return
        try:
            cls = int(self.info_vars["cls"].get())
            xc, yc, w, h = (float(self.info_vars[k].get()) for k in ("xc", "yc", "w", "h"))
        except ValueError:
            messagebox.showwarning("입력 오류", "Class는 정수, 좌표는 숫자(0~1)로 입력하세요.")
            return
        if not (0 <= cls < len(CLASS_NAMES)):
            messagebox.showwarning("입력 오류", f"Class는 0 ~ {len(CLASS_NAMES) - 1} 사이여야 합니다.")
            return
        if not (0 <= xc <= 1 and 0 <= yc <= 1 and 0 < w <= 1 and 0 < h <= 1):
            messagebox.showwarning("입력 오류", "YOLO 좌표는 0 ~ 1 사이 값이어야 합니다. (너비·높이 > 0)")
            return

        x1, y1, x2, y2 = yolo_to_bbox(xc, yc, w, h, self.img_w, self.img_h)
        x1, y1 = self.clamp_image_xy(x1, y1)
        x2, y2 = self.clamp_image_xy(x2, y2)
        self.push_history()
        self.boxes[self.selected] = {"cls": cls, "x1": x1, "y1": y1, "x2": x2, "y2": y2}
        self.mark_dirty()
        self.select_box(self.selected)
        self.canvas.focus_set()
        self.set_status("선택 BBox 정보 적용 완료")

    def update_box_list(self):
        self.box_list.delete(0, "end")
        for i, b in enumerate(self.boxes):
            self.box_list.insert("end", f" {i + 1:>2}.  [{b['cls']}] {get_class_name(b['cls'])}")
            self.box_list.itemconfig(i, foreground=get_class_color(b["cls"]))
        if self.selected is not None:
            self.box_list.selection_set(self.selected)
            self.box_list.see(self.selected)
        self.box_group.config(text=f" 이 이미지의 BBox ({len(self.boxes)}) ")

    # ==================================================
    # 2-8. 삭제 / 되돌리기
    # ==================================================

    def push_history(self):
        """변경 '직전' 상태를 저장 → Ctrl+Z 로 돌아갈 수 있게"""
        self.history.append(copy.deepcopy(self.boxes))
        del self.history[:-HISTORY_LIMIT]          # 오래된 것은 버림

    def mark_dirty(self):
        self.dirty = True
        self.update_header()

    def delete_selected(self):
        if self.selected is None:
            self.set_status("삭제할 BBox를 먼저 선택하세요. (선택 이동 모드에서 클릭)")
            return
        self.push_history()
        removed = self.boxes.pop(self.selected)
        self.selected = None
        self.mark_dirty()
        self.refresh_boxes()
        self.set_status(f"BBox 삭제: {removed['cls']} {get_class_name(removed['cls'])}  |  "
                        f"남은 BBox {len(self.boxes)}개  (Ctrl+Z 로 되돌리기)")

    def undo(self):
        if not self.history:
            self.set_status("되돌릴 작업이 없습니다.")
            return
        self.boxes = self.history.pop()
        self.selected = None
        self.mark_dirty()
        self.refresh_boxes()
        self.set_status(f"되돌리기 완료  |  BBox {len(self.boxes)}개")

    # ==================================================
    # 2-9. 저장 → 다시 불러와 확인
    # ==================================================

    def save_labels(self):
        if self.pil_image is None:
            return False
        label_path = get_label_path(self.image_paths[self.index])
        try:
            write_yolo_file(label_path, self.boxes, self.img_w, self.img_h)
        except OSError as e:
            messagebox.showerror("저장 실패", f"{label_path}\n\n{e}")
            return False

        # ⑦ 방금 쓴 TXT 를 다시 읽어서, 화면의 BBox 와 같은지 검증합니다. (QA 습관!)
        reloaded, bad_lines = read_yolo_file(label_path, self.img_w, self.img_h)
        same = len(reloaded) == len(self.boxes) and not bad_lines and all(
            a["cls"] == b["cls"] and all(abs(a[k] - b[k]) < 0.5 for k in ("x1", "y1", "x2", "y2"))
            for a, b in zip(reloaded, self.boxes))

        self.boxes = reloaded                     # 화면 = 파일 내용 그대로
        if self.selected is not None and self.selected >= len(self.boxes):
            self.selected = None
        self.dirty = False
        self.refresh_boxes()
        self.update_list_item_color(self.index)
        self.update_progress()

        try:
            shown = label_path.relative_to(self.image_root.parent)
        except ValueError:
            shown = label_path.name
        if same:
            self.set_status(f"✔ 저장 완료: {shown}  →  다시 불러와 확인 OK (BBox {len(self.boxes)}개)")
        else:
            self.set_status(f"⚠ 저장은 했지만 다시 불러온 내용이 다릅니다: {shown}")
            messagebox.showwarning("확인 필요", "저장 후 다시 불러온 BBox가 화면과 다릅니다.\nTXT 파일을 확인해 주세요.")
        return True

    def save_and_next(self):
        if self.save_labels():
            if self.index < len(self.image_paths) - 1:
                self.index += 1
                self.load_image()
            else:
                self.set_status("✔ 저장 완료  |  마지막 이미지입니다.")

    def reload_labels(self):
        """디스크의 TXT 를 다시 읽어 화면에 표시 (저장한 내용이 맞는지 눈으로 확인)"""
        if self.pil_image is None:
            return
        if self.dirty and not messagebox.askyesno(
                "다시 불러오기", "저장하지 않은 변경 내용이 사라집니다. 계속할까요?"):
            return
        label_path = get_label_path(self.image_paths[self.index])
        self.boxes, bad_lines = read_yolo_file(label_path, self.img_w, self.img_h)
        self.selected = None
        self.history = []
        self.dirty = False
        self.refresh_boxes()
        self.set_status(f"라벨 다시 불러오기 완료: BBox {len(self.boxes)}개"
                        + (f"  |  ⚠ 형식 오류 줄 {bad_lines}" if bad_lines else ""))

    # ==================================================
    # 2-10. 이전 · 다음 이미지 / 종료
    # ==================================================

    def confirm_leave(self):
        """저장 안 된 변경이 있으면 물어봅니다. 계속 진행해도 되면 True"""
        if not self.dirty:
            return True
        if self.auto_save_var.get():
            return self.save_labels()
        answer = messagebox.askyesnocancel("저장", "저장하지 않은 BBox 변경이 있습니다. 저장할까요?")
        if answer is None:                        # 취소
            return False
        if answer:                                # 예
            return self.save_labels()
        return True                               # 아니오 (버리고 진행)

    def move_to(self, new_index):
        if not self.image_paths:
            return
        if not (0 <= new_index < len(self.image_paths)):
            self.set_status("첫 번째 이미지입니다." if new_index < 0 else "마지막 이미지입니다.")
            return
        if new_index == self.index:
            return
        if not self.confirm_leave():
            self.sync_image_list()                # 목록 클릭을 취소했으면 선택 되돌리기
            return
        self.index = new_index
        self.load_image()

    def prev_image(self):
        self.move_to(self.index - 1)

    def next_image(self):
        self.move_to(self.index + 1)

    def on_image_list_select(self, event):
        sel = self.image_list.curselection()
        if sel and sel[0] != self.index:
            self.move_to(sel[0])

    def show_shortcuts(self):
        messagebox.showinfo("단축키 안내", (
            "[이미지]  A / D : 이전 / 다음\n"
            "[저장]    Ctrl+S : 저장   Ctrl+Enter : 저장 후 다음   F5 : 다시 불러오기\n"
            "[모드]    W : 새 BBox   E : 선택 이동   H : Pan\n"
            "[Class]  0 ~ 6 : Class 선택 (선택된 BBox가 있으면 바로 변경)\n"
            "[편집]    Delete : 선택 BBox 삭제   Ctrl+Z : 되돌리기   Esc : 선택 해제\n"
            "[보기]    + / - : Zoom   F : Fit   휠 : 마우스 위치 Zoom\n"
            "             오른쪽(가운데) 버튼 드래그 : 어떤 모드에서든 Pan\n\n"
            "※ 한글 입력 상태에서는 알파벳 단축키가 동작하지 않을 수 있어요."))

    def on_close(self):
        if self.confirm_leave():
            self.root.destroy()


# ==================================================
# 3. 프로그램 실행
# ==================================================

### ㅁ너난
if __name__ == "__main__":
    root = tk.Tk()
    app = LabelingApp(root)
    root.mainloop()