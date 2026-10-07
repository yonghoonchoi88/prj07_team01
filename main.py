"""
조각김치 이물검출 라벨링 프로그램 v4.0 - 프로그램 시작
=====================================================

[실행]
    pip install -r requirements.txt
    python main.py

[하는 일]
    1) configs/classes.yaml 을 읽어서 Class · 작업자 · scene_type · review_reason · 규칙을 만든다.
    2) validator 로 설정 파일이 올바른지 검사한다.
    3) 메인 화면(MainWindow)을 띄운다.

[데이터 흐름]  (교과7 산출물 기준)
    data/raw   원본 데이터셋 (읽기 전용, 절대 수정 안 함)
      ─작업자 1차 검수─▶ data/work/labels        status: DONE / EDITED / REVIEW, qa_status: WAIT
      ─검수자 교차검수─▶ data/final/images+labels qa_status: PASS   (raw → final 직행 금지)
[작업대장]  data/manifests/dataset_manifest.csv  (이미지 1장 = 1줄, 8개 컬럼)
[산출물]    검사 > 산출물 생성 → manifests/ · reports/ · docs/subject08_handoff.md
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


def load_config(path):
    """
    classes.yaml → 프로그램이 쓰기 좋은 모양으로 정리
        classes     : [{"id": 0, "name": "...", "enabled": True, "color": "#..."}, ...]
        members     : ["최용훈", "박건", ...]
        scene_types    : {"kimchi_with_target": "김치 + 검출 대상 객체", ...}   (순서 유지)
        review_reasons : {"class_ambiguous": "Class 판단이 애매함", ...}
        rules          : {"allow_self_review": False, "golden_test_size": 20, ...}
        project_dir    : 산출물(reports · manifests · docs)을 쓸 프로젝트 폴더
    """
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

    return {
        "classes": classes,
        "members": [str(m).strip() for m in data["members"]],
        "scene_types": {str(k): str(v) for k, v in data["scene_types"].items()},
        "review_reasons": {str(k): str(v) for k, v in data["review_reasons"].items()},
        "rules": dict(data.get("rules") or {}),
        "project_dir": BASE_DIR,
    }


def main():
    try:
        config = load_config(CONFIG_PATH)
    except (OSError, ValueError, yaml.YAMLError) as e:
        # 설정이 잘못되면 화면을 띄우지 않고 이유만 알려주고 끝냅니다.
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("설정 파일 오류", f"{CONFIG_PATH}\n\n{e}")
        root.destroy()
        sys.exit(1)

    root = tk.Tk()
    MainWindow(root, config)
    root.mainloop()


if __name__ == "__main__":
    main()
