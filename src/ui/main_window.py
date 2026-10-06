"""
main_window.py - 화면 구성과 버튼 · 이벤트 처리
==============================================

화면 배치, 메뉴, 단축키, 그리고 '버튼을 누르면 누구에게 일을 시킬지'를 담당합니다.
실제 일은 각 모듈이 합니다.

    BBox 데이터        → src/bbox/bbox_manager.py
    이미지/마우스 그리기 → src/ui/canvas.py
    TXT 읽기 / 쓰기     → src/yolo/yolo_loader.py, yolo_writer.py
    FINAL 전 검사       → src/validation/validator.py
    작업 기록(CSV)      → src/records/label_csv.py

[역할]
    작업자 : 저장하면 labels/Work  에만 저장 (Final 저장 불가)
    검수자 : 저장하면 labels/Final 에만 저장 (검사 통과해야 저장, Work 저장 불가)

[라벨 흐름]  RAW(원본, 읽기 전용) ─작업자─▶ WORK(작업 중) ─검수자─▶ FINAL(검수 완료)
[작업 기록]  저장할 때마다 labels/label.csv 에 파일명 · 일시 · work/final · 이름 · scene_type
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from src.bbox.bbox_manager import BBoxManager
from src.records.label_csv import LabelLog
from src.ui.canvas import ImageCanvas
from src.validation.validator import LabelValidator
from src.yolo.yolo_loader import (STAGE_FINAL, STAGE_RAW, STAGE_WORK, collect_images,
                                  find_label_to_load, find_legacy_labels, get_label_path,
                                  get_label_stages, read_yolo_file, split_label_location,
                                  yolo_to_bbox)
from src.yolo.yolo_writer import (ROLE_REVIEWER, ROLE_STAGE, ROLE_WORKER, bbox_to_yolo,
                                  can_move_to_final, copy_to_raw, format_yolo_lines,
                                  save_for_role)

APP_TITLE = "조각김치 이물검출 라벨링 프로그램 v3.1"
LABEL_CSV_NAME = "label.csv"         # labels/ 폴더 안에 생기는 작업 기록 파일

# 역할 → 화면 표시 이름 / CSV 의 work_type
ROLE_TEXT = {ROLE_WORKER: "작업자", ROLE_REVIEWER: "검수자"}
ROLE_WORK_TYPE = {ROLE_WORKER: "work", ROLE_REVIEWER: "final"}

# ---------- 디자인 ----------
FONT = "Malgun Gothic"     # 윈도우 기본 한글 폰트 (없으면 tkinter가 알아서 대체)
BG = "#EEF1F5"             # 창 배경
PANEL = "#FFFFFF"          # 패널 배경
BORDER = "#C9D1DC"
TEXT = "#1F2937"
MUTED = "#6B7280"
DISABLED = "#A0A7B2"
PRIMARY = "#1D6FE8"        # 파란 버튼 (모드 강조, 저장 후 다음)
PRIMARY_DARK = "#1557BD"
SUCCESS = "#16A34A"        # 초록 버튼 (저장)
SUCCESS_DARK = "#11823B"
FINAL_BG = "#7C3AED"       # 보라 버튼 (검수자 저장 → FINAL)
FINAL_DARK = "#6D28D9"
DANGER = "#DC2626"         # 삭제 / 저장 안 됨
SELECT_BG = "#D6E6FF"      # 목록 선택 배경

# 단계별 표시 (이미지 목록 기호, 색, 헤더 배지)
STAGE_STYLE = {
    STAGE_FINAL: ("✔", SUCCESS, "FINAL"),
    STAGE_WORK: ("✎", PRIMARY, "WORK"),
    STAGE_RAW: ("○", TEXT, "RAW"),
    None: ("·", DISABLED, "NEW"),
}


class MainWindow:
    """
    config: main.py 가 classes.yaml 에서 만든 설정
        classes     : [{"id": 0, "name": "나뭇잎·종이류", "enabled": True, "color": "#F59E0B"}, ...]
        members     : ["최용훈", "박건", "이승훈", "김하민", "심준형"]
        scene_types : {"kimchi_with_target": "김치와 이물질", ...}
    """

    def __init__(self, root, config):
        self.root = root
        self.classes = config["classes"]
        self.members = config["members"]
        self.scene_types = config["scene_types"]
        classes = self.classes
        self.root.title(APP_TITLE)
        self.root.geometry("1360x880")
        self.root.minsize(1150, 740)
        self.root.configure(bg=BG)

        # ---------- 폴더 / 이미지 ----------
        self.image_root = None       # 이미지 목록의 기준 폴더
        self.image_paths = []        # Path 목록
        self.stage_cache = []        # 이미지별 '가장 앞선 단계' (목록 색칠용)
        self.index = 0
        self.img_w = 0
        self.img_h = 0
        self.loaded_stage = None     # 지금 화면의 라벨을 어느 단계에서 읽었는지

        # ---------- 라벨 ----------
        self.manager = BBoxManager()
        self.validator = LabelValidator(classes, self.scene_types)
        self.current_class = next(c["id"] for c in classes if c["enabled"])

        # ---------- 작업 기록 (label.csv) / scene_type ----------
        self.label_log = None        # 폴더를 열면 labels/label.csv 로 만들어집니다.
        self.scene_records = {}      # {파일명: 가장 최근 scene_type}  (CSV 에서 읽어 옴)
        self.loaded_scene = ""       # 이미지를 열 때의 scene_type (바뀌었는지 비교용)

        self.mode_var = tk.StringVar(value="select")
        self.auto_save_var = tk.BooleanVar(value=False)
        self.role_var = tk.StringVar(value="")      # "worker" / "reviewer" - 둘 중 하나만
        self.name_var = tk.StringVar(value="")      # 5명 중 한 명
        self.scene_var = tk.StringVar(value="")     # scene_type

        self.setup_style()
        self.build_menu()
        self.build_ui()
        self.bind_events()
        self.set_mode("select")      # README 규칙: 'BBox 는 새로 치지 않고 기존 박스를 수정'
        self.set_current_class(self.current_class, apply_to_selected=False)
        self.update_role_ui()
        self.canvas.render()
        self.set_status("① 왼쪽 위에서 작업자/검수자와 이름을 고르고  ② 파일 > 폴더 열기 (Ctrl+O)로 시작하세요.")

    # ==================================================
    # 0. Class 도우미
    # ==================================================

    def class_name(self, cid):
        return self.classes[cid]["name"] if 0 <= cid < len(self.classes) else f"class{cid}"

    def class_color(self, cid):
        return self.classes[cid]["color"] if 0 <= cid < len(self.classes) else "#9CA3AF"

    def class_enabled(self, cid):
        return 0 <= cid < len(self.classes) and self.classes[cid]["enabled"]

    def class_style(self, cid):
        """canvas.py 에 넘겨주는 함수: Class 번호 → (이름, 색)"""
        return self.class_name(cid), self.class_color(cid)

    # ==================================================
    # 1. 화면 구성
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
        file_menu.add_command(label="저장 (작업자 → WORK / 검수자 → FINAL)", accelerator="Ctrl+S",
                              command=self.save_labels)
        file_menu.add_command(label="저장 후 다음", accelerator="Ctrl+Enter", command=self.save_and_next)
        file_menu.add_separator()
        file_menu.add_command(label="라벨 다시 불러오기", accelerator="F5", command=self.reload_labels)
        file_menu.add_command(label="RAW 원본으로 되돌리기", command=self.restore_raw)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.on_close)
        menubar.add_cascade(label="파일(F)", menu=file_menu, underline=3)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Zoom In", accelerator="+", command=lambda: self.canvas.zoom_in())
        view_menu.add_command(label="Zoom Out", accelerator="-", command=lambda: self.canvas.zoom_out())
        view_menu.add_command(label="화면에 맞춤 (Fit)", accelerator="F",
                              command=lambda: self.canvas.fit_to_window())
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
            "정보", f"{APP_TITLE}\n\n작업자 → WORK · 검수자 → FINAL · scene_type · label.csv 기록"))
        menubar.add_cascade(label="도움말(H)", menu=help_menu, underline=4)

        self.root.config(menu=menubar)

    def make_group(self, parent, title):
        """제목이 있는 흰색 박스 ('보기 도구', 'Class 선택' 같은 영역)"""
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

    # ---------- ① 왼쪽: 작업자 정보 / 이미지 목록 / scene_type ----------
    def build_left_panel(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        # --- 작업자 / 검수자 (Radiobutton = 여러 개 중 '하나만' 고르는 버튼) ---
        role_group = self.make_group(left, "작업자 정보")
        role_group.pack(fill="x")
        row = tk.Frame(role_group, bg=PANEL)
        row.pack(fill="x")
        for value in (ROLE_WORKER, ROLE_REVIEWER):
            tk.Radiobutton(row, text=f"{ROLE_TEXT[value]}  (→ {ROLE_STAGE[value].upper()})",
                           variable=self.role_var, value=value, command=self.on_role_change,
                           font=(FONT, 9), bg=PANEL, activebackground=PANEL, bd=0, highlightthickness=0,
                           cursor="hand2").pack(side="left", padx=(0, 6))
        self.name_combo = ttk.Combobox(role_group, state="readonly", font=(FONT, 10),
                                       textvariable=self.name_var, values=self.members)
        self.name_combo.pack(fill="x", pady=(4, 2))
        self.name_combo.set("")
        self.role_info = tk.Label(role_group, text="", font=(FONT, 8, "bold"), bg=PANEL,
                                  fg=DANGER, anchor="w", justify="left")
        self.role_info.pack(fill="x")

        # --- 이미지 목록 ---
        self.left_group = self.make_group(left, "이미지 목록 (0)")
        self.left_group.pack(fill="both", expand=True, pady=(10, 0))

        tk.Button(self.left_group, text="폴더 열기…", command=self.open_folder,
                  font=(FONT, 9), bg=PANEL, relief="solid", bd=1,
                  cursor="hand2", activebackground=SELECT_BG).pack(fill="x", pady=(0, 6))

        wrap = tk.Frame(self.left_group, bg=PANEL)
        wrap.pack(fill="both", expand=True)

        # exportselection=False: 다른 Listbox를 클릭해도 이 목록의 선택이 풀리지 않게!
        self.image_list = tk.Listbox(wrap, width=30, exportselection=False,
                                     font=(FONT, 9), activestyle="none",
                                     selectbackground=SELECT_BG, selectforeground=PRIMARY_DARK,
                                     bd=1, relief="solid", highlightthickness=0)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.image_list.yview)
        self.image_list.config(yscrollcommand=scroll.set)
        self.image_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.progress_label = tk.Label(self.left_group, text="FINAL 0 / 0", justify="left",
                                       font=(FONT, 9, "bold"), bg=PANEL, fg=TEXT, anchor="w")
        self.progress_label.pack(fill="x", pady=(6, 0))
        self.stage_count_label = tk.Label(self.left_group, text="WORK 0 · RAW 0 · 라벨 없음 0",
                                          font=(FONT, 8), bg=PANEL, fg=MUTED, anchor="w")
        self.stage_count_label.pack(fill="x")
        tk.Label(self.left_group, text="✔ FINAL   ✎ WORK   ○ RAW   · 라벨 없음",
                 font=(FONT, 8), bg=PANEL, fg=MUTED, anchor="w").pack(fill="x", pady=(2, 0))

        # --- scene_type (YOLO Class 가 아니라 '이미지 전체'에 대한 정보) ---
        scene_group = self.make_group(left, "scene_type (이미지 전체)")
        scene_group.pack(fill="x", pady=(10, 0))
        for key, desc in self.scene_types.items():
            tk.Radiobutton(scene_group, text=f"{key}\n   {desc}", variable=self.scene_var,
                           value=key, command=self.on_scene_change, justify="left", anchor="w",
                           font=(FONT, 9), bg=PANEL, activebackground=PANEL, bd=0, highlightthickness=0,
                           cursor="hand2").pack(fill="x")

    # ---------- ② 가운데: 파일명 + 단계 배지 + 이미지 Canvas ----------
    def build_center_panel(self, parent):
        center = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        center.grid(row=0, column=1, sticky="nsew")

        header = tk.Frame(center, bg=PANEL)
        header.pack(fill="x", padx=10, pady=6)
        self.stage_badge = tk.Label(header, text="", font=(FONT, 9, "bold"), fg="white",
                                    bg=PANEL, padx=8, pady=1)
        self.stage_badge.pack(side="left", padx=(0, 8))
        self.name_label = tk.Label(header, text="(폴더를 열어주세요)",
                                   font=(FONT, 11, "bold"), bg=PANEL, fg=TEXT)
        self.name_label.pack(side="left")
        self.count_label = tk.Label(header, text="", font=(FONT, 11, "bold"), bg=PANEL, fg=TEXT)
        self.count_label.pack(side="left", padx=18)
        self.zoom_label = tk.Label(header, text="", font=(FONT, 9), bg=PANEL, fg=MUTED)
        self.zoom_label.pack(side="right")

        self.canvas = ImageCanvas(
            center, self.manager,
            class_style=self.class_style,
            get_class=lambda: self.current_class,
            on_select=self.on_box_selected,
            on_edit=self.on_box_edited,
            on_live=self.update_info_panel,
            on_status=self.set_status,
            width=820, height=520)
        self.canvas.zoom_listener = lambda s: self.zoom_label.config(text=f"Zoom {s * 100:.0f}%")
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ---------- ③ 오른쪽: Class 선택 / 선택된 BBox 정보 / BBox 목록 ----------
    def build_right_panel(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.grid(row=0, column=2, sticky="ns", padx=(8, 0))

        # --- Class 선택 (classes.yaml 에서 읽은 목록) ---
        cls_group = self.make_group(right, "Class 선택")
        cls_group.pack(fill="x")

        labels = [f"{c['id']}. {c['name']}" + ("" if c["enabled"] else "  (사용 안 함)")
                  for c in self.classes]
        self.class_combo = ttk.Combobox(cls_group, state="readonly", width=28,
                                        font=(FONT, 10), values=labels)
        self.class_combo.pack(fill="x", pady=(0, 6))

        self.class_list = tk.Listbox(cls_group, height=len(self.classes), exportselection=False,
                                     font=(FONT, 10), activestyle="none",
                                     selectbackground=PRIMARY, selectforeground="white",
                                     bd=1, relief="solid", highlightthickness=0)
        for i, label in enumerate(labels):
            self.class_list.insert("end", f" ■  {label}")
            self.class_list.itemconfig(i, foreground=self.class_color(i)
                                       if self.classes[i]["enabled"] else DISABLED)
        self.class_list.pack(fill="x")

        tk.Label(cls_group, text="새 BBox의 Class / 선택한 BBox의 Class 변경",
                 font=(FONT, 8), bg=PANEL, fg=MUTED).pack(anchor="w", pady=(4, 0))

        # --- 현재 선택된 BBox 정보 ---
        info = self.make_group(right, "현재 선택된 BBox 정보")
        info.pack(fill="x", pady=(10, 0))

        self.info_vars = {}
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
        self.tool_button(view, "⊕", "Zoom In", lambda: self.canvas.zoom_in(), width=7)
        self.tool_button(view, "⊖", "Zoom Out", lambda: self.canvas.zoom_out(), width=7)
        self.tool_button(view, "⛶", "Fit", lambda: self.canvas.fit_to_window(), width=7)
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
        # 저장 버튼 글자/색은 역할에 따라 바뀝니다. (update_role_ui 참고)
        self.save_btn = self.tool_button(nav, "✔", "저장 (Ctrl+S)", self.save_labels, width=15)
        self.tool_button(nav, "⏭", "저장 후 다음", self.save_and_next, width=12,
                         bg=PRIMARY, fg="white", active_bg=PRIMARY_DARK)

    # ==================================================
    # 2. 이벤트 연결
    # ==================================================

    def bind_events(self):
        self.image_list.bind("<<ListboxSelect>>", self.on_image_list_select)
        self.class_combo.bind("<<ComboboxSelected>>", self.on_class_combo_select)
        self.class_list.bind("<<ListboxSelect>>", self.on_class_list_select)
        self.box_list.bind("<<ListboxSelect>>", self.on_box_list_select)
        self.name_combo.bind("<<ComboboxSelected>>", self.on_name_change)

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
                          ("f", lambda: self.canvas.fit_to_window())]:
            self.bind_key(f"<{key}>", func)
            self.bind_key(f"<{key.upper()}>", func)           # CapsLock 켜져 있어도 동작
        for seq in ("<plus>", "<equal>", "<KP_Add>"):
            self.bind_key(seq, lambda: self.canvas.zoom_in())
        for seq in ("<minus>", "<KP_Subtract>"):
            self.bind_key(seq, lambda: self.canvas.zoom_out())
        self.bind_key("<Delete>", self.delete_selected)
        self.bind_key("<BackSpace>", self.delete_selected)
        self.bind_key("<Escape>", self.on_escape)
        # 숫자키 → Class 선택. "<1>"은 마우스 버튼이라서 꼭 "<Key-1>"로 써야 합니다!
        for i in range(min(10, len(self.classes))):
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
    # 3. 폴더 열기 & 이미지 로드
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

        # 예전 위치(labels/train/a.txt)의 라벨 → RAW 로 한 번만 복사해서 원본 보관
        legacy = find_legacy_labels(paths)
        if legacy and messagebox.askyesno(
                "RAW 원본 보관",
                f"단계 폴더(Raw/Work/Final) 밖에 있는 기존 라벨 TXT {len(legacy)}개를 찾았습니다.\n\n"
                "labels/Raw 로 복사해서 원본으로 보관할까요?\n"
                "(기존 파일은 그대로 두고, Raw 에 이미 있는 파일은 덮어쓰지 않습니다)"):
            copied = copy_to_raw(legacy)
            messagebox.showinfo("RAW 원본 보관", f"{copied}개를 labels/Raw 로 복사했습니다.")

        # labels/label.csv 준비 (없으면 머리줄만 있는 파일을 새로 만듭니다)
        labels_root, _ = split_label_location(paths[0])
        try:
            self.label_log = LabelLog(labels_root / LABEL_CSV_NAME)
            self.scene_records = self.label_log.latest_scene_types()
        except (OSError, ValueError) as e:
            self.label_log, self.scene_records = None, {}
            messagebox.showwarning("label.csv", f"작업 기록 파일을 열 수 없습니다.\n{e}")

        self.image_root = image_root
        self.image_paths = paths
        self.stage_cache = [None] * len(paths)
        self.index = 0
        self.manager.dirty = False

        # 하위 폴더(train/val)가 여러 개면 'train/xxx.jpg'처럼, 아니면 파일명만 표시
        multi_dirs = len({p.parent for p in paths}) > 1
        self.list_names = [p.relative_to(image_root).as_posix() if multi_dirs else p.name
                           for p in paths]
        self.image_list.delete(0, "end")
        for i in range(len(paths)):
            self.image_list.insert("end", "")
            self.update_list_item(i)

        self.left_group.config(text=f" 이미지 목록 ({len(paths)}) ")
        self.update_progress()
        self.load_image()

    def update_list_item(self, i):
        """이미지 목록 한 줄을 단계에 맞게 기호 + 색으로 표시 (FINAL ✔ / WORK ✎ / RAW ○)"""
        stages = get_label_stages(self.image_paths[i])
        # 화면에 띄우는 순서와 같게: WORK(다시 고치는 중) > FINAL > RAW
        stage = next((s for s in (STAGE_WORK, STAGE_FINAL, STAGE_RAW) if s in stages), None)
        self.stage_cache[i] = stage
        mark, color, _ = STAGE_STYLE[stage]
        selected = self.image_list.curselection()
        self.image_list.delete(i)
        self.image_list.insert(i, f" {mark}  {self.list_names[i]}")
        self.image_list.itemconfig(i, foreground=color)
        if i in selected:
            self.image_list.selection_set(i)

    def update_progress(self):
        total = len(self.image_paths)
        count = {s: self.stage_cache.count(s) for s in (STAGE_FINAL, STAGE_WORK, STAGE_RAW, None)}
        percent = count[STAGE_FINAL] / total * 100 if total else 0
        self.progress_label.config(text=f"FINAL {count[STAGE_FINAL]} / {total}  ({percent:.0f}%)")
        self.stage_count_label.config(
            text=f"WORK {count[STAGE_WORK]} · RAW {count[STAGE_RAW]} · 라벨 없음 {count[None]}")

    def load_image(self):
        path = self.image_paths[self.index]
        try:
            with Image.open(path) as im:
                pil_image = im.convert("RGB")
        except OSError as e:
            messagebox.showerror("이미지 열기 실패", f"{path.name}\n\n{e}")
            return
        self.img_w, self.img_h = pil_image.size

        # WORK > FINAL > RAW 순서로 라벨 자동 로드
        stage, label_path = find_label_to_load(path)
        boxes, bad_lines = read_yolo_file(label_path, self.img_w, self.img_h)
        self.manager.load(boxes)
        self.loaded_stage = stage
        self.load_scene()

        self.canvas.set_image(pil_image)
        self.refresh_panels()
        self.sync_image_list()

        where = {STAGE_WORK: "WORK (작업 중)", STAGE_FINAL: "FINAL (검수 완료)",
                 STAGE_RAW: "RAW (원본)", None: "라벨 없음 → 새로 작성"}[stage]
        msg = (f"{path.name} 열기  |  원본 {self.img_w}x{self.img_h}  |  "
               f"라벨: {where}  |  BBox {len(boxes)}개  |  "
               f"scene_type: {self.loaded_scene or '미지정'}")
        if bad_lines:
            msg += f"  |  ⚠ 형식 오류 줄 {bad_lines} 건너뜀"
        if self.final_blocked():
            msg += "  |  ⚠ WORK 에 없는 파일 → 검수자는 FINAL 저장 불가 (작업자가 먼저 WORK 저장)"
        self.set_status(msg)

    def final_blocked(self):
        """검수자인데 지금 이미지가 WORK 에 없으면 True (RAW → FINAL 직행 금지)"""
        role, _ = self.current_role()
        return (role == ROLE_REVIEWER and bool(self.image_paths)
                and not can_move_to_final(self.image_paths[self.index]))

    def file_key(self, index=None):
        """label.csv 에 쓰는 파일명. 이미지 기준 폴더에서의 상대 경로 (예: train/a.jpg)"""
        i = self.index if index is None else index
        return self.image_paths[i].relative_to(self.image_root).as_posix()

    def load_scene(self):
        """label.csv 에 남아 있는 이 이미지의 마지막 scene_type 을 화면에 표시"""
        self.loaded_scene = self.scene_records.get(self.file_key(), "")
        self.scene_var.set(self.loaded_scene)

    def sync_image_list(self):
        self.image_list.selection_clear(0, "end")
        if self.image_paths:
            self.image_list.selection_set(self.index)
            self.image_list.see(self.index)

    # ==================================================
    # 4. 화면 갱신
    # ==================================================

    def refresh_panels(self):
        """BBox 가 바뀌었을 때 관련된 화면을 한꺼번에 갱신"""
        self.canvas.draw_boxes()
        self.update_info_panel()
        self.update_box_list()
        self.update_header()

    def update_header(self):
        if not self.image_paths:
            return
        dirty = self.manager.dirty
        star = "  ● 저장 안 됨" if dirty else ""
        self.name_label.config(text=self.image_paths[self.index].name + star,
                               fg=DANGER if dirty else TEXT)
        self.count_label.config(text=f"( {self.index + 1} / {len(self.image_paths)} )")
        _, color, text = STAGE_STYLE[self.loaded_stage]
        self.stage_badge.config(text=text, bg=color if self.loaded_stage != STAGE_RAW else MUTED)

    def set_status(self, text):
        self.status_label.config(text=text)

    def update_info_panel(self):
        b = self.manager.selected_box
        if b is None:
            for var in self.info_vars.values():
                var.set("")
            self.info_class_name.config(text="선택된 BBox 없음", fg=MUTED)
            return
        xc, yc, w, h = bbox_to_yolo(b["x1"], b["y1"], b["x2"], b["y2"], self.img_w, self.img_h)
        self.info_vars["cls"].set(str(b["cls"]))
        self.info_vars["xc"].set(f"{xc:.4f}")
        self.info_vars["yc"].set(f"{yc:.4f}")
        self.info_vars["w"].set(f"{w:.4f}")
        self.info_vars["h"].set(f"{h:.4f}")
        warn = "" if self.class_enabled(b["cls"]) else "  ⚠ 사용 안 함"
        self.info_class_name.config(
            text=f"#{self.manager.selected + 1}  {self.class_name(b['cls'])}{warn}  |  "
                 f"{b['x2'] - b['x1']:.0f} x {b['y2'] - b['y1']:.0f} px",
            fg=self.class_color(b["cls"]) if not warn else DANGER)

    def update_box_list(self):
        self.box_list.delete(0, "end")
        for i, b in enumerate(self.manager.boxes):
            warn = "" if self.class_enabled(b["cls"]) else "  ⚠"
            self.box_list.insert("end", f" {i + 1:>2}.  [{b['cls']}] {self.class_name(b['cls'])}{warn}")
            self.box_list.itemconfig(i, foreground=self.class_color(b["cls"]))
        if self.manager.selected is not None:
            self.box_list.selection_set(self.manager.selected)
            self.box_list.see(self.manager.selected)
        self.box_group.config(text=f" 이 이미지의 BBox ({len(self.manager.boxes)}) ")

    # ==================================================
    # 5. Canvas 에서 오는 알림 (콜백)
    # ==================================================

    def on_box_selected(self):
        b = self.manager.selected_box
        if b is not None:
            # 선택한 BBox 의 Class 를 오른쪽 Class 선택칸에도 보여줍니다. (변경 X, 표시만)
            if self.class_enabled(b["cls"]):
                self.current_class = b["cls"]
            self.show_class(b["cls"])
        self.refresh_panels()

    def on_box_edited(self, message):
        self.on_box_selected()
        self.set_status(message)

    # ==================================================
    # 5-1. 작업자 / 검수자 · scene_type
    # ==================================================

    def current_role(self):
        """(역할, 이름) - 둘 다 골라야 저장할 수 있습니다."""
        return self.role_var.get(), self.name_var.get().strip()

    def on_role_change(self):
        self.update_role_ui()
        role, name = self.current_role()
        self.set_status(f"역할: {ROLE_TEXT[role]} → 저장하면 labels/{ROLE_STAGE[role]} 에만 저장됩니다."
                        + ("" if name else "  (이름도 골라 주세요)")
                        + ("  |  ⚠ 지금 이미지는 WORK 에 없어 FINAL 저장 불가" if self.final_blocked() else ""))

    def on_name_change(self, event=None):
        self.update_role_ui()
        self.canvas.focus_set()                # 콤보박스 포커스 해제 → 단축키 계속 사용
        role, name = self.current_role()
        self.set_status(f"이름: {name}" + ("" if role else "  (작업자/검수자도 골라 주세요)"))

    def update_role_ui(self):
        """역할에 따라 저장 버튼 글자 · 색과 안내 문구를 바꿉니다."""
        role, name = self.current_role()
        if role == ROLE_REVIEWER:
            text, bg, active = "검수 저장 → FINAL", FINAL_BG, FINAL_DARK
        elif role == ROLE_WORKER:
            text, bg, active = "저장 → WORK", SUCCESS, SUCCESS_DARK
        else:
            text, bg, active = "저장 (역할 선택)", DISABLED, DISABLED
        self.save_btn.config(text=f"✔\n{text}", bg=bg, fg="white", activebackground=active,
                             activeforeground="white")

        if role and name:
            self.role_info.config(text=f"{ROLE_TEXT[role]} {name}  →  labels/{ROLE_STAGE[role]} 에만 저장",
                                  fg=SUCCESS if role == ROLE_WORKER else FINAL_BG)
        else:
            missing = " · ".join(t for t, ok in (("역할", role), ("이름", name)) if not ok)
            self.role_info.config(text=f"⚠ {missing} 을(를) 골라야 저장할 수 있습니다.", fg=DANGER)

    def on_scene_change(self):
        """scene_type 도 '변경 사항'입니다 → 저장 안 됨 표시 후, 저장하면 label.csv 에 기록"""
        scene = self.scene_var.get()
        if self.canvas.pil_image is None:
            return
        if scene != self.loaded_scene:
            self.manager.dirty = True
            self.update_header()
        self.set_status(f"scene_type: {scene} ({self.scene_types.get(scene, '')})  |  저장하면 label.csv 에 기록됩니다.")

    # ==================================================
    # 6. 모드 / Class / 정보 패널
    # ==================================================

    def set_mode(self, mode):
        self.mode_var.set(mode)
        self.canvas.set_mode(mode)
        for m, btn in self.mode_buttons.items():
            bg, fg = btn.default_colors
            if m == mode:
                btn.config(bg=PRIMARY, fg="white", activebackground=PRIMARY_DARK,
                           activeforeground="white")
            else:
                btn.config(bg=bg, fg=fg, activebackground=SELECT_BG, activeforeground=fg)
        names = {"draw": "새 BBox 그리기 (드래그)",
                 "select": "선택 이동 (클릭 선택 · 드래그 이동 · 핸들로 크기 조절)",
                 "pan": "Pan (드래그로 화면 이동)"}
        self.set_status(f"모드: {names[mode]}")

    def show_class(self, class_id):
        """Combobox / Listbox 표시만 맞춥니다. (코드로 바꾸면 Select 이벤트가 안 생겨서 무한루프 X)"""
        if not (0 <= class_id < len(self.classes)):
            return
        self.class_combo.current(class_id)
        self.class_list.selection_clear(0, "end")
        self.class_list.selection_set(class_id)
        self.class_list.see(class_id)

    def set_current_class(self, class_id, apply_to_selected=True, quiet=False):
        if not (0 <= class_id < len(self.classes)):
            return
        if not self.class_enabled(class_id):
            # classes.yaml 에서 enabled: false 인 Class 는 고를 수 없습니다.
            self.show_class(self.current_class)
            self.set_status(f"'{class_id} {self.class_name(class_id)}' 는 사용하지 않는 Class 입니다. "
                            "(configs/classes.yaml → enabled: false)")
            return

        self.current_class = class_id
        self.show_class(class_id)

        idx = self.manager.selected
        if apply_to_selected and idx is not None:
            old = self.manager.set_class(idx, class_id)
            if old is not None:
                self.refresh_panels()
                self.set_status(f"Class 변경: {old} {self.class_name(old)} → "
                                f"{class_id} {self.class_name(class_id)}")
                return
        if not quiet:
            self.set_status(f"현재 Class: {class_id} {self.class_name(class_id)}")

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
            self.manager.select(sel[0])
            self.on_box_selected()

    def on_escape(self):
        if self.canvas.cancel_drag():
            self.set_status("드래그 취소")
        else:
            self.manager.select(None)
            self.refresh_panels()

    def apply_info(self):
        """오른쪽 입력칸에서 직접 고친 Class / YOLO 좌표를 BBox 에 반영"""
        idx = self.manager.selected
        if idx is None:
            self.set_status("먼저 BBox를 선택하세요.")
            return
        try:
            cls = int(self.info_vars["cls"].get())
            xc, yc, w, h = (float(self.info_vars[k].get()) for k in ("xc", "yc", "w", "h"))
        except ValueError:
            messagebox.showwarning("입력 오류", "Class는 정수, 좌표는 숫자(0~1)로 입력하세요.")
            return
        if not (0 <= cls < len(self.classes)):
            messagebox.showwarning("입력 오류", f"Class는 0 ~ {len(self.classes) - 1} 사이여야 합니다.")
            return
        if not self.class_enabled(cls):
            messagebox.showwarning("입력 오류", f"{cls} {self.class_name(cls)} 는 사용하지 않는 Class 입니다.")
            return
        if not (0 <= xc <= 1 and 0 <= yc <= 1 and 0 < w <= 1 and 0 < h <= 1):
            messagebox.showwarning("입력 오류", "YOLO 좌표는 0 ~ 1 사이 값이어야 합니다. (너비·높이 > 0)")
            return

        x1, y1, x2, y2 = yolo_to_bbox(xc, yc, w, h, self.img_w, self.img_h)
        x1, y1 = self.canvas.clamp(x1, y1)
        x2, y2 = self.canvas.clamp(x2, y2)
        self.manager.replace(idx, {"cls": cls, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        self.on_box_selected()
        self.canvas.focus_set()
        self.set_status("선택 BBox 정보 적용 완료")

    # ==================================================
    # 7. 삭제 / 되돌리기
    # ==================================================

    def delete_selected(self):
        removed = self.manager.delete_selected()
        if removed is None:
            self.set_status("삭제할 BBox를 먼저 선택하세요. (선택 이동 모드에서 클릭)")
            return
        self.refresh_panels()
        self.set_status(f"BBox 삭제: {removed['cls']} {self.class_name(removed['cls'])}  |  "
                        f"남은 BBox {len(self.manager.boxes)}개  (Ctrl+Z 로 되돌리기)")

    def undo(self):
        if not self.manager.undo():
            self.set_status("되돌릴 작업이 없습니다.")
            return
        self.refresh_panels()
        self.set_status(f"되돌리기 완료  |  BBox {len(self.manager.boxes)}개")

    # ==================================================
    # 8. 저장 (작업자 → WORK / 검수자 → FINAL) → 다시 불러와 확인 → label.csv 기록
    # ==================================================

    def short_path(self, path):
        try:
            return path.relative_to(self.image_root.parent).as_posix()
        except ValueError:
            return path.name

    def check_before_save(self, role, name, scene):
        """저장해도 되는지 미리 확인. 괜찮으면 True"""
        if not role or not name:
            messagebox.showwarning("저장 불가", "왼쪽 위 '작업자 정보'에서\n작업자/검수자와 이름을 먼저 골라 주세요.")
            return False
        if not scene:
            messagebox.showwarning("저장 불가", "왼쪽 아래에서 scene_type 을 골라 주세요.\n"
                                   "(이미지 전체가 어떤 형태인지 기록하는 정보입니다)")
            return False

        if role != ROLE_REVIEWER:
            return True

        # FINAL 은 WORK 를 거친 파일만! (RAW 만 있거나 라벨이 없는 이미지는 바로 FINAL 불가)
        if self.final_blocked():
            where = {STAGE_FINAL: "이미 FINAL 에 있는 이미지",
                     STAGE_RAW: "RAW(원본)만 있는 이미지",
                     None: "라벨이 없는 이미지"}.get(self.loaded_stage, "WORK 에 없는 이미지")
            self.set_status("✖ WORK 에 없는 파일은 FINAL 로 옮길 수 없습니다.")
            messagebox.showwarning("FINAL 저장 불가",
                                   f"{where}입니다.\n\n"
                                   "FINAL 에는 WORK 에 있는 파일만 옮길 수 있습니다.\n"
                                   "작업자가 먼저 WORK 에 저장한 뒤 검수해 주세요.")
            return False

        # 검수자는 FINAL 에 저장하기 '전'에 내용을 검사합니다. (파일에 쓰기 전 = 메모리의 BBox 로 검사)
        boxes = self.manager.boxes
        lines = format_yolo_lines(boxes, self.img_w, self.img_h)
        errors, warnings = self.validator.check_lines(lines, self.img_w, self.img_h)
        e2, w2 = self.validator.check_scene(scene, len(boxes))
        errors, warnings = errors + e2, warnings + w2
        if errors:
            self.set_status(f"✖ 검사 실패 {len(errors)}건 → FINAL 에 저장하지 않았습니다.")
            messagebox.showerror("FINAL 저장 불가", "아래 문제를 고친 뒤 다시 저장해 주세요.\n\n"
                                 + "\n".join(errors[:12]) + ("\n..." if len(errors) > 12 else ""))
            return False
        if warnings and not messagebox.askyesno(
                "확인", "\n".join(warnings) + "\n\n그래도 FINAL 에 저장할까요?"):
            self.set_status("FINAL 저장 취소")
            return False
        return True

    def save_labels(self):
        """
        저장 버튼 하나로 역할에 맞는 폴더에만 저장합니다. RAW 는 절대 건드리지 않습니다.
            ① 역할 · 이름 · scene_type 확인 (+ 검수자는 내용 검사)
            ② TXT 저장  (작업자 → Work / 검수자 → Final)
            ③ 다시 읽어서 화면과 같은지 확인
            ④ labels/label.csv 에 한 줄 기록
        """
        if self.canvas.pil_image is None:
            return False
        role, name = self.current_role()
        scene = self.scene_var.get()
        if not self.check_before_save(role, name, scene):                      # ①
            return False

        image_path = self.image_paths[self.index]
        boxes = self.manager.boxes
        try:
            label_path = save_for_role(role, image_path, boxes, self.img_w, self.img_h)   # ②
        except OSError as e:                  # PermissionError 도 OSError 의 한 종류
            messagebox.showerror("저장 실패", str(e))
            return False

        # ③ 방금 쓴 TXT 를 다시 읽어서, 화면의 BBox 와 같은지 검증합니다. (QA 습관!)
        reloaded, bad_lines = read_yolo_file(label_path, self.img_w, self.img_h)
        same = len(reloaded) == len(boxes) and not bad_lines and all(
            a["cls"] == b["cls"] and all(abs(a[k] - b[k]) < 0.5 for k in ("x1", "y1", "x2", "y2"))
            for a, b in zip(reloaded, boxes))

        self.manager.mark_saved(reloaded)         # 화면 = 파일 내용 그대로
        self.loaded_stage = ROLE_STAGE[role]
        self.refresh_panels()
        self.update_list_item(self.index)
        self.update_progress()

        # ④ 작업 기록
        log_msg = self.write_label_log(role, name, scene)

        who = f"[{ROLE_TEXT[role]} {name}]"
        if same:
            self.set_status(f"✔ {who} {ROLE_STAGE[role].upper()} 저장: {self.short_path(label_path)}  →  "
                            f"확인 OK (BBox {len(reloaded)}개)  |  scene_type: {scene}  |  {log_msg}")
        else:
            self.set_status(f"⚠ 저장은 했지만 다시 불러온 내용이 다릅니다: {self.short_path(label_path)}")
            messagebox.showwarning("확인 필요", "저장 후 다시 불러온 BBox가 화면과 다릅니다.\nTXT 파일을 확인해 주세요.")
        return True

    def write_label_log(self, role, name, scene):
        """label.csv 에 한 줄 추가. 결과 문구를 돌려줍니다."""
        if self.label_log is None:
            return "⚠ label.csv 없음"
        try:
            self.label_log.append(self.file_key(), ROLE_WORK_TYPE[role], name, scene)
        except OSError as e:
            # 엑셀로 label.csv 를 열어 두면 윈도우가 파일을 잠가서 여기로 옵니다.
            messagebox.showwarning("label.csv 기록 실패",
                                   "TXT 는 저장했지만 label.csv 에 기록하지 못했습니다.\n"
                                   "엑셀 등에서 label.csv 를 닫고 다시 저장해 주세요.\n\n" + str(e))
            return "⚠ label.csv 기록 실패"
        self.scene_records[self.file_key()] = scene
        self.loaded_scene = scene
        return "label.csv 기록 ✔"

    def save_and_next(self):
        if self.save_labels():
            if self.index < len(self.image_paths) - 1:
                self.index += 1
                self.load_image()
            else:
                self.set_status("✔ 저장 완료  |  마지막 이미지입니다.")

    def reload_labels(self):
        """디스크의 TXT 를 다시 읽어 화면에 표시 (저장한 내용이 맞는지 눈으로 확인)"""
        if self.canvas.pil_image is None:
            return
        if self.manager.dirty and not messagebox.askyesno(
                "다시 불러오기", "저장하지 않은 변경 내용이 사라집니다. 계속할까요?"):
            return
        stage, label_path = find_label_to_load(self.image_paths[self.index])
        boxes, bad_lines = read_yolo_file(label_path, self.img_w, self.img_h)
        self.manager.load(boxes)
        self.loaded_stage = stage
        self.load_scene()
        self.refresh_panels()
        self.set_status(f"라벨 다시 불러오기 완료 ({STAGE_STYLE[stage][2]}): BBox {len(boxes)}개"
                        + (f"  |  ⚠ 형식 오류 줄 {bad_lines}" if bad_lines else ""))

    def restore_raw(self):
        """RAW 원본 BBox 를 화면에 다시 가져옵니다. (RAW 파일은 읽기만 합니다)"""
        if self.canvas.pil_image is None:
            return
        if self.current_role()[0] == ROLE_REVIEWER:
            # 검수자가 RAW 내용을 그대로 FINAL 로 보내는 '우회로'를 막습니다.
            messagebox.showinfo("RAW 되돌리기", "RAW 되돌리기는 작업자만 할 수 있습니다.\n"
                                "(RAW 내용은 WORK 를 거쳐야 FINAL 로 갈 수 있습니다)")
            return
        raw_path = get_label_path(self.image_paths[self.index], STAGE_RAW)
        if not raw_path.exists():
            messagebox.showinfo("RAW 없음", "이 이미지는 RAW 원본 라벨이 없습니다.")
            return
        boxes, _ = read_yolo_file(raw_path, self.img_w, self.img_h)
        self.manager.replace_all(boxes)
        self.refresh_panels()
        self.set_status(f"RAW 원본 BBox {len(boxes)}개로 되돌렸습니다. 저장하면 역할에 맞는 폴더에 반영됩니다. "
                        "(Ctrl+Z 로 취소)")

    # ==================================================
    # 9. 이전 · 다음 이미지 / 종료
    # ==================================================

    def confirm_leave(self):
        """저장 안 된 변경이 있으면 물어봅니다. 계속 진행해도 되면 True"""
        if not self.manager.dirty:
            return True
        if self.final_blocked():
            # 검수자는 이 이미지를 어차피 저장할 수 없으니 '버리고 이동'만 물어봅니다.
            return messagebox.askyesno("저장 불가", "WORK 에 없는 이미지라 FINAL 에 저장할 수 없습니다.\n"
                                       "변경 내용을 버리고 이동할까요?")
        if self.auto_save_var.get():
            return self.save_labels()
        role, _ = self.current_role()
        where = f"{ROLE_STAGE[role].upper()} 에 " if role else ""
        answer = messagebox.askyesnocancel("저장", f"저장하지 않은 변경(BBox / scene_type)이 있습니다. {where}저장할까요?")
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
            "[저장]    Ctrl+S : 저장 (작업자 → WORK / 검수자 → FINAL)\n"
            "             Ctrl+Enter : 저장 후 다음   F5 : 다시 불러오기\n"
            "[모드]    W : 새 BBox   E : 선택 이동   H : Pan\n"
            f"[Class]  0 ~ {len(self.classes) - 1} : Class 선택 (선택된 BBox가 있으면 바로 변경)\n"
            "[편집]    Delete : 선택 BBox 삭제   Ctrl+Z : 되돌리기   Esc : 선택 해제\n"
            "[보기]    + / - : Zoom   F : Fit   휠 : 마우스 위치 Zoom\n"
            "             오른쪽(가운데) 버튼 드래그 : 어떤 모드에서든 Pan\n\n"
            "※ 한글 입력 상태에서는 알파벳 단축키가 동작하지 않을 수 있어요."))

    def on_close(self):
        if self.confirm_leave():
            self.root.destroy()
