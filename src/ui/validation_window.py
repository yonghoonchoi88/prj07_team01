"""
validation_window.py - 전체 Validation 결과 창
=============================================

    ┌ 요약 : 전체 900 · PASS 887 · FAIL 13 · 오류 종류별 건수
    └ FAIL 목록 : 더블클릭하면 그 이미지로 바로 이동 → 고치고 저장 → [다시 검사]

이 창은 결과를 '보여주기'만 합니다. 검사는 validator.validate_dataset() 가 합니다.
"""

import tkinter as tk
from tkinter import ttk

from src.validation.validator import ERROR_TYPES

FONT = "Malgun Gothic"


class ValidationWindow(tk.Toplevel):
    """
    on_jump(index)  : 목록에서 이미지를 더블클릭했을 때 (index = 이미지 번호)
    on_rerun()      : [다시 검사] 버튼 → 새 결과를 돌려주는 함수
    """

    def __init__(self, parent, result, on_jump, on_rerun):
        super().__init__(parent)
        self.title("전체 Validation 결과")
        self.geometry("760x560")
        self.configure(bg="#FFFFFF")
        self.on_jump = on_jump
        self.on_rerun = on_rerun
        self.rows = []

        self.summary = tk.Label(self, text="", justify="left", anchor="w", bg="#FFFFFF",
                                font=(FONT, 10), padx=14, pady=10)
        self.summary.pack(fill="x")

        filt = tk.Frame(self, bg="#FFFFFF")
        filt.pack(fill="x", padx=14)
        tk.Label(filt, text="오류 종류", bg="#FFFFFF", font=(FONT, 9)).pack(side="left")
        self.type_var = tk.StringVar(value="전체")
        self.type_combo = ttk.Combobox(filt, state="readonly", width=28, textvariable=self.type_var,
                                       values=["전체"] + list(ERROR_TYPES.values()))
        self.type_combo.pack(side="left", padx=6)
        self.type_combo.bind("<<ComboboxSelected>>", lambda e: self.fill_list())
        tk.Label(filt, text="  ※ 더블클릭 → 그 이미지로 이동", bg="#FFFFFF", fg="#6B7280",
                 font=(FONT, 9)).pack(side="left")

        wrap = tk.Frame(self, bg="#FFFFFF")
        wrap.pack(fill="both", expand=True, padx=14, pady=8)
        self.listbox = tk.Listbox(wrap, font=(FONT, 9), activestyle="none", bd=1, relief="solid",
                                  selectbackground="#D6E6FF", selectforeground="#1F2937")
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.listbox.yview)
        self.listbox.config(yscrollcommand=scroll.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.listbox.bind("<Double-Button-1>", self.on_double)

        btns = tk.Frame(self, bg="#FFFFFF")
        btns.pack(fill="x", padx=14, pady=(0, 12))
        tk.Button(btns, text="다시 검사", command=self.rerun, font=(FONT, 9), width=12).pack(side="left")
        tk.Button(btns, text="닫기", command=self.destroy, font=(FONT, 9), width=10).pack(side="right")
        self.show(result)

    def show(self, result):
        self.result = result
        counts = result.by_type()
        lines = [f"검사 시각 {result.run_at}",
                 f"전체 {result.total}장  ·  PASS {result.pass_count}장  ·  FAIL {result.fail_count}건"
                 + (f"  (짝 없는 파일 {len(result.orphans)}건 포함)" if result.orphans else "")]
        found = [f"{name} {counts[k]}" for k, name in ERROR_TYPES.items() if counts[k]]
        lines.append("오류 종류: " + (" · ".join(found) if found else "없음 ✔"))
        self.summary.config(text="\n".join(lines), fg="#16A34A" if not result.fail_count else "#1F2937")
        self.fill_list()

    def fill_list(self):
        want = self.type_var.get()
        code = next((k for k, v in ERROR_TYPES.items() if v == want), None)
        self.rows = [r for r in self.result.failed
                     if code is None or any(c == code for c, _ in r["errors"])]
        self.listbox.delete(0, "end")
        for r in self.rows:
            msg = " / ".join(m for _, m in r["errors"])
            self.listbox.insert("end", f" {r['file_name']}  [{r['stage']}]  {msg}")
        if not self.rows:
            self.listbox.insert("end", " FAIL 없음 ✔")

    def on_double(self, event):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.rows) and self.rows[sel[0]]["index"] is not None:
            self.on_jump(self.rows[sel[0]]["index"])

    def rerun(self):
        result = self.on_rerun()
        if result is not None:
            self.show(result)
