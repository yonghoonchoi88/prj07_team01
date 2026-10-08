"""
main_window.py - 화면 구성과 버튼 · 이벤트 처리
==============================================

화면 배치, 메뉴, 단축키, 그리고 '버튼을 누르면 누구에게 일을 시킬지'를 담당합니다.
실제 일은 각 모듈이 합니다.

    BBox 데이터          → src/bbox/bbox_manager.py
    이미지/마우스 그리기   → src/ui/canvas.py
    TXT 읽기 / 쓰기       → src/yolo/yolo_loader.py, yolo_writer.py
    검사 (한 장 / 900장)  → src/validation/validator.py
    작업대장 · 이력       → src/records/manifest.py, history.py
    자동 테스트 · 산출물   → src/qa/self_test.py, reports.py

[작업 흐름]  (교과7 산출물 기준)
    raw (원본, 읽기 전용)
      → 작업자 1차 검수 → work   status: DONE(수정 없음) / EDITED(수정함) / REVIEW(+사유)   qa: WAIT
      → 검수자 교차검수 → final  qa: PASS   (또는 반려 → REVIEW 로 work 에 남김)
      → 전체 Validation → 산출물 생성 (manifest · QA Summary · Test Report · Handoff)
"""

import io
import tkinter as tk
import zipfile
from contextlib import redirect_stdout
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from PIL import Image

from src.bbox.bbox_manager import BBoxManager
from src.qa.reports import export_all, make_handoff_package
from src.qa.self_test import run_tests
from src.records.history import ACTION_PASS, ACTION_REJECT, ACTION_WORK, History
from src.records.manifest import (QA_PASS, QA_WAIT, STATUS_DONE, STATUS_EDITED, STATUS_REVIEW,
                                  Manifest)
from src.ui.canvas import ImageCanvas
from src.ui.validation_window import ValidationWindow
from src.validation.validator import LabelValidator, save_run, validate_dataset
from tools.merge_results import merge, pack
from src.yolo.yolo_loader import (STAGE_FINAL, STAGE_RAW, STAGE_WORK, build_workspace,
                                  find_label_to_load, label_signature, read_yolo_file, yolo_to_bbox)
from src.yolo.yolo_writer import (ROLE_REVIEWER, ROLE_WORKER, bbox_to_yolo, can_move_to_final,
                                  format_yolo_lines, pass_to_final, save_work)

APP_TITLE = "조각김치 이물검출 라벨링 프로그램 v4.1"
ROLE_TEXT = {ROLE_WORKER: "작업자", ROLE_REVIEWER: "검수자"}

# ---------- 디자인 ----------
FONT = "Malgun Gothic"     # 윈도우 기본 한글 폰트 (없으면 tkinter가 알아서 대체)
BG = "#EEF1F5"
PANEL = "#FFFFFF"
BORDER = "#C9D1DC"
TEXT = "#1F2937"
MUTED = "#6B7280"
DISABLED = "#A0A7B2"
PRIMARY = "#1D6FE8"
PRIMARY_DARK = "#1557BD"
SUCCESS = "#16A34A"
SUCCESS_DARK = "#11823B"
FINAL_BG = "#7C3AED"
FINAL_DARK = "#6D28D9"
ORANGE = "#EA580C"         # REVIEW
ORANGE_DARK = "#C2410C"
DANGER = "#DC2626"
SELECT_BG = "#D6E6FF"

# 헤더 배지: 지금 화면의 라벨을 어디서 읽었는지
STAGE_STYLE = {STAGE_FINAL: (SUCCESS, "FINAL"), STAGE_WORK: (PRIMARY, "WORK"),
               STAGE_RAW: (MUTED, "RAW"), None: (DISABLED, "NEW")}

# 이미지 목록 필터 (manifest 한 줄 → 보일지 말지)
FILTERS = {
    "전체": lambda r, me: True,
    "미작업 (1차 검수 전)": lambda r, me: not r["status"],
    "QA 대기 (DONE · EDITED)": lambda r, me: r["status"] in (STATUS_DONE, STATUS_EDITED) and r["qa_status"] != QA_PASS,
    "REVIEW": lambda r, me: r["status"] == STATUS_REVIEW,
    "QA PASS": lambda r, me: r["qa_status"] == QA_PASS,
    "내가 1차 검수한 것": lambda r, me: bool(me) and r["worker"] == me,
}


def row_style(row):
    """manifest 한 줄 → (목록 기호, 색, 짧은 상태)"""
    if row["qa_status"] == QA_PASS:
        return "✔", SUCCESS, "PASS"
    if row["status"] == STATUS_REVIEW:
        return "⚑", ORANGE, "REVIEW"
    if row["status"] in (STATUS_DONE, STATUS_EDITED):
        return "✎", PRIMARY, "QA 대기"
    return "○", DISABLED, "미작업"


class MainWindow:
    """
    config: main.py 가 classes.yaml 에서 만든 설정
        classes, members, scene_types, review_reasons, rules, project_dir
    """

    def __init__(self, root, config):
        self.root = root
        self.classes = config["classes"]
        self.members = config["members"]
        self.scene_types = config["scene_types"]
        self.reasons = config["review_reasons"]
        self.rules = config.get("rules", {})
        self.project_dir = config["project_dir"]
        self.root.title(APP_TITLE)
        self.root.geometry("1366x900")
        self.root.minsize(1200, 760)
        self.root.configure(bg=BG)

        # ---------- 작업 공간 ----------
        self.ws = None
        self.items = []              # ImageItem 목록
        self.manifest = None         # dataset_manifest.csv (이미지 1장 = 1줄)
        self.history = None          # label_history.csv (작업 일지)
        self.index = 0
        self.view = []               # 필터를 통과한 이미지 번호들 (목록에 보이는 순서)
        self.view_pos = {}           # {이미지 번호: 목록 줄 번호}
        self.img_w = self.img_h = 0
        self.loaded_stage = None
        self.raw_sig = []            # 원본(raw) 라벨 지문 → DONE / EDITED 자동 판정
        self.loaded_meta = ("", False, "")   # 열 때의 (scene_type, REVIEW 여부, 사유)
        self.last_result = None      # 마지막 전체 Validation 결과
        self.golden = self.pilot = None
        self.vwin = None

        # ---------- 라벨 ----------
        self.manager = BBoxManager()
        self.validator = LabelValidator(self.classes, self.scene_types)
        self.current_class = next(c["id"] for c in self.classes if c["enabled"])

        self.mode_var = tk.StringVar(value="select")
        self.auto_save_var = tk.BooleanVar(value=False)
        self.role_var = tk.StringVar(value="")
        self.name_var = tk.StringVar(value="")
        self.scene_var = tk.StringVar(value="")
        self.review_var = tk.BooleanVar(value=False)
        self.reason_var = tk.StringVar(value="")
        self.filter_var = tk.StringVar(value="전체")

        self.setup_style()
        self.build_menu()
        self.build_ui()
        self.bind_events()
        self.set_mode("select")      # BBox 기준: 새로 치기보다 기존 박스를 확인 · 수정
        self.set_current_class(self.current_class, apply_to_selected=False)
        self.update_role_ui()
        self.update_status_panel()
        self.canvas.render()
        self.set_status("① 왼쪽 위에서 작업자/검수자와 이름을 고르고  ② 파일 > 폴더 열기 (Ctrl+O) 로 data 폴더를 여세요.")

    # ==================================================
    # 0. 도우미
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

    @property
    def item(self):
        return self.items[self.index] if self.items else None

    def row(self, index=None):
        i = self.index if index is None else index
        return self.manifest.get(self.items[i].key)

    def reason_key(self):
        """콤보박스 글자 'class_ambiguous — Class 판단이 애매함' → 'class_ambiguous'"""
        return self.reason_var.get().split(" — ")[0].strip()

    def reason_label(self, key):
        return f"{key} — {self.reasons[key]}" if key in self.reasons else key

    def busy(self, on):
        self.root.config(cursor="watch" if on else "")
        self.root.update_idletasks()

    # ==================================================
    # 1. 화면 구성
    # ==================================================

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", padding=3)
        self.root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    def build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="data 폴더 열기...", accelerator="Ctrl+O", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="저장", accelerator="Ctrl+S", command=self.save_labels)
        file_menu.add_command(label="저장 후 다음", accelerator="Ctrl+Enter", command=self.save_and_next)
        file_menu.add_separator()
        file_menu.add_command(label="라벨 다시 불러오기 (Reload)", accelerator="F5", command=self.reload_labels)
        file_menu.add_command(label="RAW 원본으로 되돌리기 (작업자)", command=self.restore_raw)
        file_menu.add_separator()
        file_menu.add_command(label="내 결과 묶음 만들기 (팀 공유용 zip)...", command=self.pack_results)
        file_menu.add_command(label="팀원 결과 묶음 합치기...", command=self.merge_results)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.on_close)
        menubar.add_cascade(label="파일(F)", menu=file_menu, underline=3)

        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Zoom In", accelerator="+", command=lambda: self.canvas.zoom_in())
        view_menu.add_command(label="Zoom Out", accelerator="-", command=lambda: self.canvas.zoom_out())
        view_menu.add_command(label="화면에 맞춤 (Fit)", accelerator="F", command=lambda: self.canvas.fit_to_window())
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

        qa_menu = tk.Menu(menubar, tearoff=0)
        qa_menu.add_command(label="전체 Validation (모든 이미지)", accelerator="F7", command=self.run_validation)
        qa_menu.add_command(label="Golden · Pilot 자동 테스트 실행", command=self.run_self_tests)
        qa_menu.add_separator()
        qa_menu.add_command(label="산출물 생성 (Manifest · QA Summary · Test Report · Handoff)",
                            command=self.export_reports)
        qa_menu.add_command(label="교과 8 Handoff 패키지 만들기...", command=self.make_handoff)
        menubar.add_cascade(label="검사(Q)", menu=qa_menu, underline=3)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="단축키 안내", command=self.show_shortcuts)
        help_menu.add_command(label="프로그램 정보", command=lambda: messagebox.showinfo(
            "정보", f"{APP_TITLE}\n\nraw → 1차 검수(work) → 교차검수(final)\n"
                    "Dataset Manifest · Validation · QA Summary · Test Report"))
        menubar.add_cascade(label="도움말(H)", menu=help_menu, underline=4)
        self.root.config(menu=menubar)

    def make_group(self, parent, title):
        return tk.LabelFrame(parent, text=f" {title} ", font=(FONT, 10, "bold"), bg=PANEL, fg=TEXT,
                             bd=1, relief="solid", padx=8, pady=5, labelanchor="nw")

    def tool_button(self, parent, icon, text, command, width=9, bg=PANEL, fg=TEXT, active_bg=SELECT_BG):
        btn = tk.Button(parent, text=f"{icon}\n{text}", command=command, width=width, font=(FONT, 9),
                        bg=bg, fg=fg, activebackground=active_bg, activeforeground=fg, relief="solid",
                        bd=1, cursor="hand2", padx=3, pady=2)
        btn.pack(side="left", padx=2)
        btn.default_colors = (bg, fg)
        return btn

    def build_ui(self):
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        main = tk.Frame(self.root, bg=BG)
        main.grid(row=0, column=0, sticky="nsew", padx=10, pady=(8, 4))
        main.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        self.build_left_panel(main)
        self.build_center_panel(main)
        self.build_right_panel(main)
        self.build_toolbar()
        self.status_label = tk.Label(self.root, text="", anchor="w", bg="#E2E7EE", fg=TEXT,
                                     font=(FONT, 9), padx=10, pady=3)
        self.status_label.grid(row=2, column=0, sticky="ew")

    # ---------- ① 왼쪽: 작업자 정보 / 이미지 목록 / scene_type ----------
    def build_left_panel(self, parent):
        left = tk.Frame(parent, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        role_group = self.make_group(left, "작업자 정보")
        role_group.pack(fill="x")
        row = tk.Frame(role_group, bg=PANEL)
        row.pack(fill="x")
        for value, text in ((ROLE_WORKER, "작업자 (1차 검수)"), (ROLE_REVIEWER, "검수자 (교차검수)")):
            tk.Radiobutton(row, text=text, variable=self.role_var, value=value, command=self.on_role_change,
                           font=(FONT, 9), bg=PANEL, activebackground=PANEL, bd=0, highlightthickness=0,
                           cursor="hand2").pack(side="left", padx=(0, 6))
        self.name_combo = ttk.Combobox(role_group, state="readonly", font=(FONT, 10),
                                       textvariable=self.name_var, values=self.members)
        self.name_combo.pack(fill="x", pady=(3, 2))
        self.role_info = tk.Label(role_group, text="", font=(FONT, 8, "bold"), bg=PANEL, fg=DANGER,
                                  anchor="w", justify="left")
        self.role_info.pack(fill="x")

        self.left_group = self.make_group(left, "이미지 목록 (0)")
        self.left_group.pack(fill="both", expand=True, pady=(8, 0))
        top = tk.Frame(self.left_group, bg=PANEL)
        top.pack(fill="x", pady=(0, 4))
        tk.Button(top, text="폴더 열기…", command=self.open_folder, font=(FONT, 9), bg=PANEL, relief="solid",
                  bd=1, cursor="hand2", activebackground=SELECT_BG).pack(side="left")
        self.filter_combo = ttk.Combobox(top, state="readonly", font=(FONT, 9), width=22,
                                         textvariable=self.filter_var, values=list(FILTERS))
        self.filter_combo.pack(side="right", fill="x", expand=True, padx=(6, 0))

        wrap = tk.Frame(self.left_group, bg=PANEL)
        wrap.pack(fill="both", expand=True)
        self.image_list = tk.Listbox(wrap, width=36, exportselection=False, font=(FONT, 9),
                                     activestyle="none", selectbackground=SELECT_BG,
                                     selectforeground=PRIMARY_DARK, bd=1, relief="solid", highlightthickness=0)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.image_list.yview)
        self.image_list.config(yscrollcommand=scroll.set)
        self.image_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.progress_label = tk.Label(self.left_group, text="QA PASS 0 / 0", font=(FONT, 9, "bold"),
                                       bg=PANEL, fg=TEXT, anchor="w")
        self.progress_label.pack(fill="x", pady=(5, 0))
        self.count_detail = tk.Label(self.left_group, text="", font=(FONT, 8), bg=PANEL, fg=MUTED, anchor="w")
        self.count_detail.pack(fill="x")
        tk.Label(self.left_group, text="✔ PASS   ✎ QA 대기   ⚑ REVIEW   ○ 미작업", font=(FONT, 8),
                 bg=PANEL, fg=MUTED, anchor="w").pack(fill="x", pady=(1, 0))

        scene_group = self.make_group(left, "scene_type (이미지 전체)")
        scene_group.pack(fill="x", pady=(8, 0))
        for key, desc in self.scene_types.items():
            tk.Radiobutton(scene_group, text=f"{key}  ·  {desc}", variable=self.scene_var, value=key,
                           command=self.on_meta_change, anchor="w", font=(FONT, 8), bg=PANEL,
                           activebackground=PANEL, bd=0, highlightthickness=0, cursor="hand2").pack(fill="x")

    # ---------- ② 가운데 ----------
    def build_center_panel(self, parent):
        center = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        center.grid(row=0, column=1, sticky="nsew")
        header = tk.Frame(center, bg=PANEL)
        header.pack(fill="x", padx=10, pady=6)
        self.stage_badge = tk.Label(header, text="", font=(FONT, 9, "bold"), fg="white", bg=PANEL, padx=7)
        self.stage_badge.pack(side="left", padx=(0, 8))
        self.name_label = tk.Label(header, text="(data 폴더를 열어주세요)", font=(FONT, 11, "bold"),
                                   bg=PANEL, fg=TEXT)
        self.name_label.pack(side="left")
        self.count_label = tk.Label(header, text="", font=(FONT, 10, "bold"), bg=PANEL, fg=TEXT)
        self.count_label.pack(side="left", padx=12)
        self.origin_label = tk.Label(header, text="", font=(FONT, 9, "bold"), bg="#EEF2FF", fg="#4338CA", padx=7)
        self.origin_label.pack(side="left")
        self.state_chip = tk.Label(header, text="", font=(FONT, 9, "bold"), fg="white", bg=PANEL, padx=7)
        self.state_chip.pack(side="left", padx=8)
        self.zoom_label = tk.Label(header, text="", font=(FONT, 9), bg=PANEL, fg=MUTED)
        self.zoom_label.pack(side="right")

        self.canvas = ImageCanvas(center, self.manager, class_style=self.class_style,
                                  get_class=lambda: self.current_class, on_select=self.on_box_selected,
                                  on_edit=self.on_box_edited, on_live=self.update_info_panel,
                                  on_status=self.set_status, width=600, height=480)
        self.canvas.zoom_listener = lambda s: self.zoom_label.config(text=f"Zoom {s * 100:.0f}%")
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ---------- ③ 오른쪽: Class / BBox 정보 / 검수 상태 / BBox 목록 ----------
    def build_right_panel(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.grid(row=0, column=2, sticky="ns", padx=(8, 0))

        cls_group = self.make_group(right, "Class 선택")
        cls_group.pack(fill="x")
        labels = [f"{c['id']}. {c['name']}" + ("" if c["enabled"] else "  (사용 안 함)") for c in self.classes]
        self.class_combo = ttk.Combobox(cls_group, state="readonly", width=30, font=(FONT, 10), values=labels)
        self.class_combo.pack(fill="x", pady=(0, 4))
        self.class_list = tk.Listbox(cls_group, height=len(self.classes), exportselection=False, font=(FONT, 9),
                                     activestyle="none", selectbackground=PRIMARY, selectforeground="white",
                                     bd=1, relief="solid", highlightthickness=0)
        for i, label in enumerate(labels):
            self.class_list.insert("end", f" ■  {label}")
            self.class_list.itemconfig(i, foreground=self.class_color(i) if self.classes[i]["enabled"] else DISABLED)
        self.class_list.pack(fill="x")

        info = self.make_group(right, "선택된 BBox 정보")
        info.pack(fill="x", pady=(8, 0))
        self.info_vars = {}
        fields = [("Class", "cls"), ("X중심", "xc"), ("Y중심", "yc"), ("너비", "w"), ("높이", "h")]
        for i, (title, key) in enumerate(fields):
            r, c = (0, 0) if i == 0 else ((i + 1) // 2, ((i + 1) % 2) * 2)
            tk.Label(info, text=title, font=(FONT, 8), bg=PANEL, fg=TEXT, anchor="w").grid(
                row=r, column=c, sticky="w", padx=(0, 3), pady=1)
            var = tk.StringVar()
            entry = tk.Entry(info, textvariable=var, width=9, font=(FONT, 9), relief="solid", bd=1)
            entry.grid(row=r, column=c + 1, sticky="ew", pady=1, padx=(0, 6))
            entry.bind("<Return>", lambda e: self.apply_info())
            self.info_vars[key] = var
        tk.Button(info, text="적용 (Enter)", command=self.apply_info, font=(FONT, 8), bg=PANEL, relief="solid",
                  bd=1, cursor="hand2").grid(row=0, column=2, columnspan=2, sticky="ew", padx=(0, 6))
        self.info_class_name = tk.Label(info, text="선택된 BBox 없음", font=(FONT, 8), bg=PANEL, fg=MUTED, anchor="w")
        self.info_class_name.grid(row=3, column=0, columnspan=4, sticky="w", pady=(2, 0))

        # --- 검수 상태 (manifest 의 status · review_reason) ---
        st = self.make_group(right, "검수 상태 (status)")
        st.pack(fill="x", pady=(8, 0))
        self.auto_status_label = tk.Label(st, text="", font=(FONT, 9, "bold"), bg=PANEL, fg=MUTED,
                                          anchor="w", justify="left")
        self.auto_status_label.pack(fill="x")
        tk.Checkbutton(st, text="REVIEW  (판단이 어려움 → 추가 검수 필요)", variable=self.review_var,
                       command=self.on_review_toggle, font=(FONT, 9), bg=PANEL, activebackground=PANEL,
                       fg=ORANGE, selectcolor=PANEL, bd=0, highlightthickness=0, anchor="w").pack(fill="x", pady=(3, 0))
        self.reason_combo = ttk.Combobox(st, state="disabled", font=(FONT, 9), textvariable=self.reason_var,
                                         values=[self.reason_label(k) for k in self.reasons])
        self.reason_combo.pack(fill="x", pady=(2, 3))
        self.qa_label = tk.Label(st, text="", font=(FONT, 8), bg=PANEL, fg=MUTED, anchor="w", justify="left")
        self.qa_label.pack(fill="x")

        self.box_group = self.make_group(right, "이 이미지의 BBox (0)")
        self.box_group.pack(fill="both", expand=True, pady=(8, 0))
        wrap = tk.Frame(self.box_group, bg=PANEL)
        wrap.pack(fill="both", expand=True)
        self.box_list = tk.Listbox(wrap, height=4, exportselection=False, font=(FONT, 9), activestyle="none",
                                   selectbackground=SELECT_BG, selectforeground=TEXT, bd=1, relief="solid",
                                   highlightthickness=0)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.box_list.yview)
        self.box_list.config(yscrollcommand=scroll.set)
        self.box_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    # ---------- ④ 아래 툴바 ----------
    def build_toolbar(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 6))

        view = self.make_group(bar, "보기 도구")
        view.pack(side="left")
        self.tool_button(view, "⊕", "Zoom In", lambda: self.canvas.zoom_in(), width=6)
        self.tool_button(view, "⊖", "Zoom Out", lambda: self.canvas.zoom_out(), width=7)
        self.tool_button(view, "⛶", "Fit", lambda: self.canvas.fit_to_window(), width=5)
        pan_btn = self.tool_button(view, "✋", "Pan", lambda: self.set_mode("pan"), width=5)

        label = self.make_group(bar, "라벨 도구")
        label.pack(side="left", padx=8)
        draw_btn = self.tool_button(label, "＋", "새 BBox", lambda: self.set_mode("draw"), width=7)
        select_btn = self.tool_button(label, "➤", "선택 이동", lambda: self.set_mode("select"), width=8)
        self.tool_button(label, "✕", "삭제", self.delete_selected, width=5, fg=DANGER)
        self.mode_buttons = {"draw": draw_btn, "select": select_btn, "pan": pan_btn}

        qa = self.make_group(bar, "검사 · 산출물")
        qa.pack(side="left")
        self.tool_button(qa, "✓", "Validation", self.run_validation, width=9)
        self.tool_button(qa, "▤", "산출물 생성", self.export_reports, width=9)

        nav = self.make_group(bar, "이미지 이동 및 저장")
        nav.pack(side="right")
        self.tool_button(nav, "◀", "이전 (A)", self.prev_image, width=7)
        self.tool_button(nav, "▶", "다음 (D)", self.next_image, width=7)
        self.save_btn = self.tool_button(nav, "✔", "저장", self.save_labels, width=14)
        self.tool_button(nav, "⏭", "저장 후 다음", self.save_and_next, width=10,
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
        self.filter_combo.bind("<<ComboboxSelected>>", self.on_filter_change)
        self.reason_combo.bind("<<ComboboxSelected>>", lambda e: (self.on_meta_change(), self.canvas.focus_set()))

        self.bind_key("<Control-o>", self.open_folder, allow_in_entry=True)
        self.bind_key("<Control-s>", self.save_labels, allow_in_entry=True)
        self.bind_key("<Control-Return>", self.save_and_next, allow_in_entry=True)
        self.bind_key("<Control-z>", self.undo)
        self.bind_key("<F5>", self.reload_labels, allow_in_entry=True)
        self.bind_key("<F7>", self.run_validation, allow_in_entry=True)
        for key, func in [("a", self.prev_image), ("d", self.next_image),
                          ("w", lambda: self.set_mode("draw")), ("e", lambda: self.set_mode("select")),
                          ("h", lambda: self.set_mode("pan")), ("f", lambda: self.canvas.fit_to_window())]:
            self.bind_key(f"<{key}>", func)
            self.bind_key(f"<{key.upper()}>", func)
        for seq in ("<plus>", "<equal>", "<KP_Add>"):
            self.bind_key(seq, lambda: self.canvas.zoom_in())
        for seq in ("<minus>", "<KP_Subtract>"):
            self.bind_key(seq, lambda: self.canvas.zoom_out())
        self.bind_key("<Delete>", self.delete_selected)
        self.bind_key("<BackSpace>", self.delete_selected)
        self.bind_key("<Escape>", self.on_escape)
        for i in range(min(10, len(self.classes))):
            self.bind_key(f"<Key-{i}>", lambda i=i: self.set_current_class(i))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def bind_key(self, sequence, func, allow_in_entry=False):
        """입력칸(Entry · Combobox)에 글자를 치는 중에는 알파벳 단축키를 양보합니다."""
        def handler(event):
            if not allow_in_entry and self.is_typing():
                return None
            func()
            return "break"
        self.root.bind(sequence, handler)

    def is_typing(self):
        try:
            widget = self.root.focus_get()
        except (KeyError, tk.TclError):
            return False
        return isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Spinbox))

    # ==================================================
    # 3. data 폴더 열기 & 이미지 목록
    # ==================================================

    def open_folder(self):
        if not self.confirm_leave():
            return
        folder = filedialog.askdirectory(title="data 폴더 선택 (안에 raw/ 가 있으면 raw 의 원본 데이터셋을 사용)")
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder):
        ws = build_workspace(folder)
        if not ws.items:
            messagebox.showwarning("이미지 없음", "선택한 폴더(하위 폴더 포함)에 이미지가 없습니다.\n"
                                   "data/raw/ 안에 원본 데이터셋 폴더를 넣었는지 확인해 주세요.")
            return
        try:
            manifest = Manifest(ws.manifest_path, ws.items)
            history = History(ws.history_path)
        except OSError as e:
            messagebox.showerror("manifest", f"작업대장을 만들 수 없습니다. (엑셀로 열려 있나요?)\n\n{e}")
            return

        self.ws, self.items, self.manifest, self.history = ws, ws.items, manifest, history
        self.index = 0
        self.manager.dirty = False
        self.last_result = None
        multi = len({(it.source_dataset, it.original_split) for it in self.items}) > 1
        short = {"validation": "val"}
        self.list_names = [f"[{' · '.join(short.get(t, t) for t in (it.source_dataset, it.original_split) if t)}] {it.key}"
                           if multi and it.origin_text else it.key for it in self.items]
        self.rebuild_list()
        self.update_progress()
        self.load_image()
        notes = []
        if ws.raw_dir == ws.root:
            notes.append("data/raw 폴더가 없어서 data 아래 전체를 원본으로 사용합니다.")
        if ws.renamed:
            notes.append(f"다른 데이터셋과 이름이 같은 이미지 {ws.renamed}장은 이름 앞에 출처를 붙였습니다. (예: dataset2_train__a.jpg)")
        if notes:
            messagebox.showinfo("data 폴더", "\n\n".join(notes))

    def rebuild_list(self):
        """필터에 맞는 이미지만 목록에 다시 채웁니다."""
        if not self.items:
            return
        rule = FILTERS[self.filter_var.get()]
        me = self.name_var.get().strip()
        self.view = [i for i, it in enumerate(self.items) if rule(self.manifest.get(it.key), me)]
        self.view_pos = {i: r for r, i in enumerate(self.view)}
        self.image_list.delete(0, "end")
        for r, i in enumerate(self.view):
            mark, color, _ = row_style(self.row(i))
            self.image_list.insert("end", f" {mark}  {self.list_names[i]}")
            self.image_list.itemconfig(r, foreground=color)
        self.left_group.config(text=f" 이미지 목록 ({len(self.view)} / {len(self.items)}) ")
        self.sync_image_list()

    def update_list_item(self, i):
        r = self.view_pos.get(i)
        if r is None:
            return
        mark, color, _ = row_style(self.row(i))
        selected = self.image_list.curselection()
        self.image_list.delete(r)
        self.image_list.insert(r, f" {mark}  {self.list_names[i]}")
        self.image_list.itemconfig(r, foreground=color)
        if r in selected:
            self.image_list.selection_set(r)

    def update_progress(self):
        c = self.manifest.counts()
        self.progress_label.config(text=f"QA PASS {c['PASS']} / {c['total']}  ({c['PASS'] / c['total'] * 100:.0f}%)")
        self.count_detail.config(text=f"QA 대기 {c['WAIT_QA']} · REVIEW {c['REVIEW']} · 미작업 {c['TODO']}  "
                                      f"(DONE {c['DONE']} · EDITED {c['EDITED']})")

    def sync_image_list(self):
        self.image_list.selection_clear(0, "end")
        r = self.view_pos.get(self.index)
        if r is not None:
            self.image_list.selection_set(r)
            self.image_list.see(r)

    def on_filter_change(self, event=None):
        self.canvas.focus_set()
        self.rebuild_list()
        if self.view and self.index not in self.view_pos:
            self.move_to(self.view[0])
        self.set_status(f"필터: {self.filter_var.get()} → {len(self.view)}장  (A / D 는 이 목록 안에서 이동)")

    # ==================================================
    # 4. 이미지 열기
    # ==================================================

    def load_image(self):
        it = self.item
        try:
            with Image.open(it.path) as im:
                pil_image = im.convert("RGB")
        except OSError as e:
            messagebox.showerror("이미지 열기 실패", f"{it.path.name}\n\n{e}")
            return
        self.img_w, self.img_h = pil_image.size

        stage, label_path = find_label_to_load(it)                  # work > final > raw
        boxes, bad_lines = read_yolo_file(label_path, self.img_w, self.img_h)
        raw_boxes, _ = read_yolo_file(it.label_path(STAGE_RAW), self.img_w, self.img_h)
        self.raw_sig = label_signature(raw_boxes, self.img_w, self.img_h)
        self.manager.load(boxes)
        self.loaded_stage = stage
        self.load_meta()

        self.canvas.set_image(pil_image)
        self.refresh_panels()
        self.sync_image_list()
        where = {STAGE_WORK: "WORK (1차 검수 결과)", STAGE_FINAL: "FINAL (QA PASS)",
                 STAGE_RAW: "RAW (원본)", None: "라벨 없음"}[stage]
        msg = (f"{it.path.name}  |  {it.origin_text}  |  {self.img_w}x{self.img_h}  |  라벨: {where}  |  "
               f"BBox {len(boxes)}개  (원본 {len(raw_boxes)}개)")
        if bad_lines:
            msg += f"  |  ⚠ 형식 오류 줄 {bad_lines} 건너뜀"
        if self.final_blocked():
            msg += "  |  ⚠ 아직 1차 검수 전 → 검수자는 QA 불가"
        self.set_status(msg)

    def load_meta(self):
        """manifest 의 scene_type · status · review_reason 을 화면에 표시"""
        row = self.row()
        self.scene_var.set(row["scene_type"])
        review = row["status"] == STATUS_REVIEW
        self.review_var.set(review)
        self.reason_var.set(self.reason_label(row["review_reason"]) if row["review_reason"] else "")
        self.reason_combo.config(state="readonly" if review else "disabled")
        self.loaded_meta = self.current_meta()
        self.update_role_ui()

    def current_meta(self):
        return self.scene_var.get(), self.review_var.get(), self.reason_key() if self.review_var.get() else ""

    def final_blocked(self):
        """검수자인데 아직 work(1차 검수 결과)가 없으면 True  (raw → final 직행 금지)"""
        return (self.current_role()[0] == ROLE_REVIEWER and self.items
                and not can_move_to_final(self.item))

    # ==================================================
    # 5. 화면 갱신
    # ==================================================

    def refresh_panels(self):
        self.canvas.draw_boxes()
        self.update_info_panel()
        self.update_box_list()
        self.update_status_panel()
        self.update_header()

    def update_header(self):
        if not self.items:
            return
        dirty = self.manager.dirty
        self.name_label.config(text=self.item.key + ("  ● 저장 안 됨" if dirty else ""),
                               fg=DANGER if dirty else TEXT)
        pos = self.view_pos.get(self.index)
        where = f"목록 {pos + 1}/{len(self.view)} · " if pos is not None and len(self.view) != len(self.items) else ""
        self.count_label.config(text=f"( {where}{self.index + 1} / {len(self.items)} )")
        self.origin_label.config(text=self.item.origin_text)
        color, text = STAGE_STYLE[self.loaded_stage]
        self.stage_badge.config(text=text, bg=color)
        row = self.row()
        _, color, short = row_style(row)
        chip = f"{row['status'] or '미작업'} · {row['qa_status']}"
        self.state_chip.config(text=chip, bg=color if short != "미작업" else DISABLED)

    def computed_status(self):
        """REVIEW 체크 → REVIEW, 아니면 원본(raw)과 같으면 DONE, 다르면 EDITED"""
        if self.review_var.get():
            return STATUS_REVIEW
        return STATUS_DONE if self.current_sig() == self.raw_sig else STATUS_EDITED

    def current_sig(self):
        return label_signature(self.manager.boxes, self.img_w, self.img_h) if self.img_w else []

    def update_status_panel(self):
        if not self.items:
            self.auto_status_label.config(text="원본 대비: -")
            self.qa_label.config(text="")
            return
        same = self.current_sig() == self.raw_sig
        auto = STATUS_DONE if same else STATUS_EDITED
        text = (f"원본 대비: {auto}  (BBox {len(self.raw_sig)} → {len(self.manager.boxes)}개)"
                + ("" if same else "\n수정 · 추가 · 삭제가 있으면 EDITED"))
        self.auto_status_label.config(text=text, fg=SUCCESS if same else PRIMARY)
        if self.review_var.get():
            self.auto_status_label.config(text=f"저장될 상태: REVIEW  (원본 대비 {auto})", fg=ORANGE)
        row = self.row()
        self.qa_label.config(text=f"QA: {row['qa_status']}  ·  1차 검수: {row['worker'] or '-'}")

    def set_status(self, text):
        self.status_label.config(text=text)

    def update_info_panel(self):
        b = self.manager.selected_box
        if b is None:
            for var in self.info_vars.values():
                var.set("")
            self.info_class_name.config(text="선택된 BBox 없음", fg=MUTED)
            self.update_status_panel()
            return
        xc, yc, w, h = bbox_to_yolo(b["x1"], b["y1"], b["x2"], b["y2"], self.img_w, self.img_h)
        self.info_vars["cls"].set(str(b["cls"]))
        for k, v in (("xc", xc), ("yc", yc), ("w", w), ("h", h)):
            self.info_vars[k].set(f"{v:.4f}")
        warn = "" if self.class_enabled(b["cls"]) else "  ⚠ 사용 안 함 → REVIEW"
        self.info_class_name.config(text=f"#{self.manager.selected + 1}  {self.class_name(b['cls'])}{warn}  |  "
                                         f"{b['x2'] - b['x1']:.0f} x {b['y2'] - b['y1']:.0f} px",
                                    fg=DANGER if warn else self.class_color(b["cls"]))
        self.update_status_panel()

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
    # 6. Canvas 알림 / 작업자 · scene_type · REVIEW
    # ==================================================

    def on_box_selected(self):
        b = self.manager.selected_box
        if b is not None:
            if self.class_enabled(b["cls"]):
                self.current_class = b["cls"]
            self.show_class(b["cls"])
        self.refresh_panels()

    def on_box_edited(self, message):
        self.on_box_selected()
        self.set_status(message)

    def current_role(self):
        return self.role_var.get(), self.name_var.get().strip()

    def on_role_change(self):
        self.update_role_ui()
        role, name = self.current_role()
        tip = {ROLE_WORKER: "저장하면 data/work 에 1차 검수 결과 (DONE / EDITED / REVIEW)",
               ROLE_REVIEWER: "QA PASS → data/final  ·  REVIEW 체크 후 저장 → 반려"}[role]
        self.set_status(f"역할: {ROLE_TEXT[role]} → {tip}" + ("" if name else "  (이름도 골라 주세요)"))

    def on_name_change(self, event=None):
        self.update_role_ui()
        self.canvas.focus_set()
        if self.filter_var.get() == "내가 1차 검수한 것":
            self.rebuild_list()

    def update_role_ui(self):
        role, name = self.current_role()
        if role == ROLE_REVIEWER and self.review_var.get():
            text, bg, active = "반려 → REVIEW", ORANGE, ORANGE_DARK
        elif role == ROLE_REVIEWER:
            text, bg, active = "QA PASS → FINAL", FINAL_BG, FINAL_DARK
        elif role == ROLE_WORKER:
            text, bg, active = "저장 → WORK", SUCCESS, SUCCESS_DARK
        else:
            text, bg, active = "저장 (역할 선택)", DISABLED, DISABLED
        self.save_btn.config(text=f"✔\n{text}", bg=bg, fg="white", activebackground=active,
                             activeforeground="white")
        if role and name:
            where = "data/work (1차 검수)" if role == ROLE_WORKER else "data/final (QA PASS) · 반려"
            self.role_info.config(text=f"{ROLE_TEXT[role]} {name}  →  {where}",
                                  fg=SUCCESS if role == ROLE_WORKER else FINAL_BG)
        else:
            missing = " · ".join(t for t, ok in (("역할", role), ("이름", name)) if not ok)
            self.role_info.config(text=f"⚠ {missing} 을(를) 골라야 저장할 수 있습니다.", fg=DANGER)

    def on_review_toggle(self):
        on = self.review_var.get()
        self.reason_combo.config(state="readonly" if on else "disabled")
        if not on:
            self.reason_var.set("")
        self.on_meta_change()
        self.update_role_ui()
        self.update_status_panel()
        if on and not self.reason_key():
            self.set_status("REVIEW 사유를 골라 주세요. (Class 기준서 · BBox 기준서의 '애매한 경우')")

    def on_meta_change(self):
        """scene_type · REVIEW · 사유도 '변경 사항' → 저장 안 됨 표시"""
        if not self.items:
            return
        if self.current_meta() != self.loaded_meta:
            self.manager.dirty = True
        self.update_header()
        self.update_status_panel()

    # ==================================================
    # 7. 모드 / Class / 정보 패널
    # ==================================================

    def set_mode(self, mode):
        self.mode_var.set(mode)
        self.canvas.set_mode(mode)
        for m, btn in self.mode_buttons.items():
            bg, fg = btn.default_colors
            if m == mode:
                btn.config(bg=PRIMARY, fg="white", activebackground=PRIMARY_DARK, activeforeground="white")
            else:
                btn.config(bg=bg, fg=fg, activebackground=SELECT_BG, activeforeground=fg)
        names = {"draw": "새 BBox 그리기 (드래그)", "select": "선택 이동 (클릭 선택 · 드래그 이동 · 핸들로 크기 조절)",
                 "pan": "Pan (드래그로 화면 이동)"}
        self.set_status(f"모드: {names[mode]}")

    def show_class(self, class_id):
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
                self.set_status(f"Class 변경: {old} {self.class_name(old)} → {class_id} {self.class_name(class_id)}")
                return
        if not quiet:
            self.set_status(f"현재 Class: {class_id} {self.class_name(class_id)}")

    def on_class_combo_select(self, event):
        self.set_current_class(self.class_combo.current())
        self.canvas.focus_set()

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
        if not (0 <= cls < len(self.classes)) or not self.class_enabled(cls):
            messagebox.showwarning("입력 오류", "사용할 수 있는 Class 번호를 입력하세요.")
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
    # 8. 저장 (작업자: work / 검수자: QA PASS → final 또는 반려)
    # ==================================================

    def check_common(self, role, name, scene):
        if not role or not name:
            messagebox.showwarning("저장 불가", "왼쪽 위 '작업자 정보'에서 작업자/검수자와 이름을 먼저 골라 주세요.")
            return False
        if not scene:
            messagebox.showwarning("저장 불가", "왼쪽 아래에서 scene_type 을 골라 주세요.")
            return False
        if self.review_var.get() and self.reason_key() not in self.reasons:
            messagebox.showwarning("저장 불가", "REVIEW 사유(review_reason)를 골라 주세요.")
            return False
        if any(not self.class_enabled(b["cls"]) for b in self.manager.boxes) and not self.review_var.get():
            # Class 기준서: Class 4 는 임의 삭제하지 않고 REVIEW → 팀 기준에 따라 확인
            if not messagebox.askyesno("사용하지 않는 Class 발견",
                                       "사용하지 않는 Class(4 고무장갑) BBox 가 있습니다.\n\n"
                                       "Class 기준서에 따라 임의로 지우지 말고\n"
                                       "REVIEW (unused_class_found) 로 저장할까요?"):
                return False
            self.review_var.set(True)
            self.reason_combo.config(state="readonly")
            self.reason_var.set(self.reason_label("unused_class_found"))
            self.update_role_ui()
        return True

    def save_labels(self):
        """
        저장 버튼 하나로 역할 · REVIEW 여부에 맞게 처리합니다. raw 는 절대 건드리지 않습니다.
            작업자         → work 저장,  status = DONE / EDITED / REVIEW,  qa = WAIT
            검수자 + REVIEW → 반려: work 저장, status = REVIEW, qa = WAIT
            검수자          → 검사 통과 시 QA PASS: final(TXT + 이미지), qa = PASS
        저장 후에는 TXT 를 다시 읽어 화면과 같은지 확인(Reload)하고 manifest · 이력을 갱신합니다.
        """
        if not self.items or self.canvas.pil_image is None:
            return False
        role, name = self.current_role()
        scene = self.scene_var.get()
        if self.final_blocked():
            messagebox.showwarning("QA 불가", "아직 1차 검수(work 저장) 전인 이미지입니다.\n\n"
                                   "raw → final 직행은 금지입니다. 작업자가 먼저 1차 검수를 해 주세요.")
            return False
        if not self.check_common(role, name, scene):
            return False

        it, row = self.item, self.row()
        boxes = self.manager.boxes
        status = self.computed_status()
        reason = self.reason_key() if status == STATUS_REVIEW else ""

        try:
            if role == ROLE_WORKER:
                if row["qa_status"] == QA_PASS and not messagebox.askyesno(
                        "QA PASS 된 이미지", "이미 QA PASS 된 이미지입니다.\n다시 저장하면 final 에서 빠지고 "
                        "QA 를 다시 받아야 합니다(WAIT).\n\n계속할까요?"):
                    return False
                path, revoked = save_work(it, boxes, self.img_w, self.img_h)
                action, fields = ACTION_WORK, dict(scene_type=scene, worker=name, status=status,
                                                   qa_status=QA_WAIT, review_reason=reason)
                stage = STAGE_WORK
            else:
                if status == STATUS_REVIEW:                      # 반려
                    path, revoked = save_work(it, boxes, self.img_w, self.img_h)
                    action, stage = ACTION_REJECT, STAGE_WORK
                    fields = dict(scene_type=scene, status=status, qa_status=QA_WAIT, review_reason=reason)
                else:                                            # QA PASS
                    if not self.rules.get("allow_self_review", False) and row["worker"] == name:
                        messagebox.showwarning("교차검수", f"{name} 님이 1차 검수한 이미지입니다.\n"
                                               "교차검수 원칙에 따라 다른 검수자가 QA PASS 해야 합니다.")
                        return False
                    lines = format_yolo_lines(boxes, self.img_w, self.img_h)
                    errors, warnings = self.validator.check_before_pass(lines, scene, self.img_w, self.img_h)
                    if errors:
                        messagebox.showerror("QA PASS 불가", "아래 문제를 고친 뒤 다시 저장하세요.\n\n"
                                             + "\n".join(errors[:12]))
                        self.set_status(f"✖ 검사 실패 {len(errors)}건 → FINAL 로 보내지 않았습니다.")
                        return False
                    if warnings and not messagebox.askyesno("확인", "\n".join(warnings) + "\n\nQA PASS 할까요?"):
                        return False
                    path, revoked = pass_to_final(it, boxes, self.img_w, self.img_h), False
                    action, stage = ACTION_PASS, STAGE_FINAL
                    fields = dict(scene_type=scene, status=status, qa_status=QA_PASS, review_reason="")
        except OSError as e:
            messagebox.showerror("저장 실패", str(e))
            return False

        # 저장한 TXT 를 다시 읽어서 화면과 같은지 확인 (Reload 검증)
        reloaded, bad = read_yolo_file(path, self.img_w, self.img_h)
        same = len(reloaded) == len(boxes) and not bad and all(
            a["cls"] == b["cls"] and all(abs(a[k] - b[k]) < 0.5 for k in ("x1", "y1", "x2", "y2"))
            for a, b in zip(reloaded, boxes))
        self.manager.mark_saved(reloaded)
        self.loaded_stage = stage

        log_ok = self.write_records(it, fields, action, role, name, len(reloaded))
        self.loaded_meta = self.current_meta()
        self.refresh_panels()
        self.update_list_item(self.index)
        self.update_progress()

        done = {ACTION_WORK: f"WORK 저장 ({status})", ACTION_REJECT: f"반려 → REVIEW ({reason})",
                ACTION_PASS: f"QA PASS → FINAL ({status})"}[action]
        msg = f"✔ [{ROLE_TEXT[role]} {name}] {done}  |  Reload 확인 {'OK' if same else '⚠ 다름'} (BBox {len(reloaded)}개)"
        if revoked:
            msg += "  |  final 에서 뺌 → QA 다시 필요"
        if not log_ok:
            msg += "  |  ⚠ manifest 기록 실패"
        self.set_status(msg)
        if not same:
            messagebox.showwarning("확인 필요", "저장 후 다시 불러온 BBox가 화면과 다릅니다. TXT 파일을 확인해 주세요.")
        return True

    def write_records(self, it, fields, action, role, name, bbox_count):
        """manifest 갱신 + 이력 한 줄. 실패하면 False (TXT 는 이미 저장된 상태)"""
        try:
            self.manifest.update(it.key, **fields)
            row = self.manifest.get(it.key)
            self.history.append(file_name=it.key, action=action, user=name, role=role,
                                status=row["status"], qa_status=row["qa_status"],
                                review_reason=row["review_reason"], scene_type=row["scene_type"],
                                bbox_count=bbox_count)
            return True
        except OSError as e:
            messagebox.showwarning("manifest 기록 실패",
                                   "TXT 는 저장했지만 dataset_manifest.csv 에 기록하지 못했습니다.\n"
                                   "엑셀에서 파일을 닫고 같은 이미지를 다시 저장해 주세요.\n\n" + str(e))
            return False

    def save_and_next(self):
        if self.save_labels():
            nxt = self.neighbor(+1)
            if self.filter_var.get() != "전체":
                self.rebuild_list()           # 저장해서 필터 조건이 바뀌었을 수 있음
            if nxt is not None:
                self.index = nxt
                self.load_image()
            else:
                self.set_status("✔ 저장 완료  |  목록의 마지막 이미지입니다.")

    def reload_labels(self):
        if not self.items:
            return
        if self.manager.dirty and not messagebox.askyesno("다시 불러오기", "저장하지 않은 변경이 사라집니다. 계속할까요?"):
            return
        self.load_image()
        self.set_status("라벨 · 상태를 디스크에서 다시 불러왔습니다. (Reload)")

    def restore_raw(self):
        if not self.items:
            return
        if self.current_role()[0] == ROLE_REVIEWER:
            messagebox.showinfo("RAW 되돌리기", "RAW 되돌리기는 작업자만 할 수 있습니다.\n"
                                "(RAW 내용은 1차 검수를 거쳐야 FINAL 로 갈 수 있습니다)")
            return
        raw_path = self.item.label_path(STAGE_RAW)
        if not raw_path.exists():
            messagebox.showinfo("RAW 없음", "이 이미지는 원본 라벨이 없습니다.")
            return
        boxes, _ = read_yolo_file(raw_path, self.img_w, self.img_h)
        self.manager.replace_all(boxes)
        self.refresh_panels()
        self.set_status(f"RAW 원본 BBox {len(boxes)}개로 되돌렸습니다. (Ctrl+Z 로 취소)")

    # ==================================================
    # 9. 검사 · 테스트 · 산출물
    # ==================================================

    def need_workspace(self):
        if not self.items:
            messagebox.showinfo("안내", "먼저 data 폴더를 열어 주세요.")
            return False
        return True

    def validate_now(self):
        self.busy(True)
        try:
            result = validate_dataset(self.ws, self.manifest, self.validator)
            save_run(result, self.ws.runs_path)
        finally:
            self.busy(False)
        self.last_result = result
        self.set_status(f"Validation: 전체 {result.total}장 · PASS {result.pass_count} · FAIL {result.fail_count}건")
        return result

    def run_validation(self):
        if not self.need_workspace() or not self.confirm_leave():
            return
        result = self.validate_now()
        if self.vwin is not None and self.vwin.winfo_exists():
            self.vwin.show(result)
            self.vwin.lift()
        else:
            self.vwin = ValidationWindow(self.root, result, on_jump=self.jump_to, on_rerun=self.validate_now)

    def jump_to(self, index):
        if index not in self.view_pos:
            self.filter_var.set("전체")
            self.rebuild_list()
        self.move_to(index)
        self.root.lift()

    def run_self_tests(self):
        if not self.need_workspace():
            return
        g = self.rules.get("golden_test_size", 20)
        p = self.rules.get("pilot_test_size", 50)
        self.set_status(f"Golden {g}장 · Pilot {p}장 자동 테스트 실행 중… (원본은 바꾸지 않습니다)")
        self.busy(True)
        try:
            self.golden = run_tests(self.items, g, self.classes, self.validator)
            self.pilot = run_tests(self.items, p, self.classes, self.validator, offset=max(1, len(self.items) // (2 * p)))
        finally:
            self.busy(False)
        lines = [f"{name}: Golden {self.golden['per_test'][name]}/{self.golden['n']} · "
                 f"Pilot {self.pilot['per_test'][name]}/{self.pilot['n']}" for name in self.golden["per_test"]]
        messagebox.showinfo("자동 테스트 결과",
                            f"Golden {self.golden['image_pass']}/{self.golden['n']} · "
                            f"Pilot {self.pilot['image_pass']}/{self.pilot['n']} PASS\n\n" + "\n".join(lines)
                            + "\n\n'산출물 생성'을 누르면 reports/test_report.md 에 기록됩니다.")
        self.set_status("자동 테스트 완료 → 검사 > 산출물 생성 으로 Test Report 에 기록하세요.")

    def export_reports(self):
        if not self.need_workspace() or not self.confirm_leave():
            return
        if self.golden is None and messagebox.askyesno(
                "Test Report", "Golden · Pilot 자동 테스트를 아직 실행하지 않았습니다.\n지금 실행할까요? (수십 초 걸릴 수 있음)"):
            self.run_self_tests()
        result = self.validate_now()
        self.busy(True)
        try:
            written, n = export_all(self.project_dir, self.ws, self.manifest, self.history.read_all(), result,
                                    self.classes, self.reasons, self.golden, self.pilot)
        except OSError as e:
            messagebox.showerror("산출물 생성 실패", str(e))
            return
        finally:
            self.busy(False)
        rel = "\n".join(f"  • {p.relative_to(self.project_dir)}" for p in written)
        c = n["counts"]
        messagebox.showinfo("산출물 생성 완료",
                            f"프로젝트 폴더: {self.project_dir}\n\n{rel}\n\n"
                            f"QA PASS {c['PASS']}/{n['total']} · Validation FAIL {n['fail_now']} · REVIEW {c['REVIEW']}")
        self.set_status(f"산출물 생성 완료 ({len(written)}개 파일) → git add 로 커밋하세요. (data/ 는 올리지 않음)")

    def make_handoff(self):
        if not self.need_workspace():
            return
        out = self.ws.root.parent / "handoff_subject08"
        if not messagebox.askyesno("교과 8 Handoff", f"아래 폴더에 FINAL 데이터와 문서를 복사합니다.\n\n{out}\n\n"
                                   "(Git 에는 올리지 않는 폴더입니다. 산출물 생성도 함께 실행합니다)"):
            return
        self.export_reports()
        self.busy(True)
        try:
            make_handoff_package(self.ws, self.project_dir, out)
        finally:
            self.busy(False)
        messagebox.showinfo("교과 8 Handoff", f"완료: {out}")

    def pack_results(self):
        """내 work · final TXT 와 manifest 를 zip 하나로 (원본 이미지는 넣지 않음)"""
        if not self.need_workspace() or not self.confirm_leave():
            return
        name = self.name_var.get().strip() or "결과"
        path = filedialog.asksaveasfilename(title="결과 묶음 저장", defaultextension=".zip",
                                            initialdir=str(self.ws.root.parent),
                                            initialfile=f"{name}_{datetime.now():%m%d_%H%M}.zip",
                                            filetypes=[("zip", "*.zip")])
        if not path:
            return
        out = io.StringIO()
        with redirect_stdout(out):
            pack(self.ws.root, path)
        messagebox.showinfo("결과 묶음", out.getvalue() + "\n이 zip 을 팀장(또는 팀원)에게 전달하세요.")

    def merge_results(self):
        """팀원 zip 들을 내 data 폴더에 합치기 (같은 이미지는 가장 최근 작업이 이김)"""
        if not self.need_workspace() or not self.confirm_leave():
            return
        paths = filedialog.askopenfilenames(title="합칠 결과 묶음(zip) 선택", initialdir=str(self.ws.root.parent),
                                            filetypes=[("zip", "*.zip")])
        if not paths:
            return
        out = io.StringIO()
        with redirect_stdout(out):
            merge(self.ws.root, list(paths), dry_run=True)
        preview = out.getvalue()
        if not messagebox.askyesno("합치기 미리보기", self.short_text(preview) + "\n\n이대로 합칠까요?"):
            return
        out = io.StringIO()
        self.busy(True)
        try:
            with redirect_stdout(out):
                merge(self.ws.root, list(paths))
        except (OSError, ValueError, zipfile.BadZipFile) as e:
            messagebox.showerror("합치기 실패", str(e))
            return
        finally:
            self.busy(False)
        current = self.item.key
        self.manager.dirty = False
        self.load_folder(str(self.ws.root))                # 합친 결과로 목록 · 상태 새로 읽기
        keys = [it.key for it in self.items]
        if current in keys:
            self.move_to(keys.index(current))
        messagebox.showinfo("합치기 완료", self.short_text(out.getvalue()))

    @staticmethod
    def short_text(text, limit=25):
        lines = text.strip().splitlines()
        return "\n".join(lines[:limit] + ([f"... (외 {len(lines) - limit}줄)"] if len(lines) > limit else []))

    # ==================================================
    # 10. 이동 / 종료
    # ==================================================

    def confirm_leave(self):
        if not self.manager.dirty:
            return True
        if self.final_blocked():
            return messagebox.askyesno("저장 불가", "1차 검수 전 이미지라 검수자는 저장할 수 없습니다.\n"
                                       "변경 내용을 버리고 진행할까요?")
        if self.auto_save_var.get():
            return self.save_labels()
        answer = messagebox.askyesnocancel("저장", "저장하지 않은 변경(BBox · scene_type · REVIEW)이 있습니다. 저장할까요?")
        if answer is None:
            return False
        if answer:
            return self.save_labels()
        return True

    def neighbor(self, step):
        """필터 목록 안에서 이전 / 다음 이미지 번호 (지금 이미지가 목록에 없으면 가장 가까운 것)"""
        if not self.view:
            return None
        pos = self.view_pos.get(self.index)
        if pos is not None:
            p = pos + step
            return self.view[p] if 0 <= p < len(self.view) else None
        if step > 0:
            return next((i for i in self.view if i > self.index), None)
        return next((i for i in reversed(self.view) if i < self.index), None)

    def move_to(self, new_index):
        if not self.items or new_index is None:
            return
        if new_index == self.index:
            self.sync_image_list()
            return
        if not self.confirm_leave():
            self.sync_image_list()
            return
        self.index = new_index
        self.load_image()

    def prev_image(self):
        nxt = self.neighbor(-1)
        if nxt is None:
            self.set_status("목록의 첫 번째 이미지입니다.")
        self.move_to(nxt)

    def next_image(self):
        nxt = self.neighbor(+1)
        if nxt is None:
            self.set_status("목록의 마지막 이미지입니다.")
        self.move_to(nxt)

    def on_image_list_select(self, event):
        sel = self.image_list.curselection()
        if sel and sel[0] < len(self.view) and self.view[sel[0]] != self.index:
            self.move_to(self.view[sel[0]])

    def show_shortcuts(self):
        messagebox.showinfo("단축키 안내", (
            "[이미지]  A / D : 이전 / 다음 (필터 목록 안에서)\n"
            "[저장]    Ctrl+S : 저장   Ctrl+Enter : 저장 후 다음   F5 : Reload\n"
            "[검사]    F7 : 전체 Validation\n"
            "[모드]    W : 새 BBox   E : 선택 이동   H : Pan\n"
            f"[Class]  0 ~ {len(self.classes) - 1} : Class 선택 (선택된 BBox가 있으면 바로 변경)\n"
            "[편집]    Delete : 선택 BBox 삭제   Ctrl+Z : 되돌리기   Esc : 선택 해제\n"
            "[보기]    + / - : Zoom   F : Fit   휠 : 마우스 위치 Zoom\n"
            "             오른쪽(가운데) 버튼 드래그 : 어떤 모드에서든 Pan\n\n"
            "※ 한글 입력 상태에서는 알파벳 단축키가 동작하지 않을 수 있어요."))

    def on_close(self):
        if self.confirm_leave():
            self.root.destroy()
