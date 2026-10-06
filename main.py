"""
조각김치 이물검출 라벨링 프로그램 v2.0 - 프로그램 시작
=====================================================

[실행]
    pip install -r requirements.txt
    python main.py

[하는 일]
    1) configs/classes.yaml 을 읽어서 Class 목록을 만든다.
    2) validator 로 설정 파일이 올바른지 검사한다.
    3) 메인 화면(MainWindow)을 띄운다.

[라벨 흐름]  labels/Raw (원본) ─저장─▶ labels/Work ─완료─▶ labels/Final
"""

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import yaml

from src.ui.main_window import MainWindow
from src.validation.validator import validate_config

BASE_DIR = Path(__file__).resolve().parent          # main.py 가 있는 폴더 (어디서 실행해도 OK)
CONFIG_PATH = BASE_DIR / "configs" / "classes.yaml"

# classes.yaml 에 color 가 없을 때 쓰는 기본 색 (class_id 순서)
DEFAULT_COLORS = ["#F59E0B", "#E91E63", "#16A34A", "#2563EB", "#9333EA", "#B45309", "#0891B2",
                  "#DB2777", "#65A30D", "#0EA5E9"]


def load_classes(path):
    """classes.yaml → [{"id": 0, "name": "...", "enabled": True, "color": "#..."}, ...]"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    errors = validate_config(data)
    if errors:
        raise ValueError("\n".join(errors))

    classes = []
    for cid in sorted(data["classes"]):                 # 0, 1, 2 ... 순서 = YOLO class_id
        info = data["classes"][cid]
        classes.append({
            "id": cid,
            "name": str(info["name"]).strip(),
            "enabled": info.get("enabled", True),
            "color": info.get("color") or DEFAULT_COLORS[cid % len(DEFAULT_COLORS)],
        })
    return classes


def main():
    try:
        classes = load_classes(CONFIG_PATH)
    except (OSError, ValueError, yaml.YAMLError) as e:
        # 설정이 잘못되면 화면을 띄우지 않고 이유만 알려주고 끝냅니다.
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("설정 파일 오류", f"{CONFIG_PATH}\n\n{e}")
        root.destroy()
        sys.exit(1)

    root = tk.Tk()
    MainWindow(root, classes)
    root.mainloop()


if __name__ == "__main__":
    main()
