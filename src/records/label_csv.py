"""
label_csv.py - 라벨 작업 기록 (labels/label.csv)
===============================================

저장할 때마다 '누가 · 언제 · 어떤 이미지를 · Work/Final 중 어디에 · 어떤 scene_type 으로'
저장했는지 한 줄씩 덧붙입니다. (지우거나 고치지 않고 계속 쌓는 '작업 일지')

    file_name,work_date,work_type,worker,scene_type
    train/a.jpg,2026-10-06 14:23:05,work,최용훈,kimchi_with_target
    train/a.jpg,2026-10-06 15:02:41,final,박건,kimchi_with_target

    work_type : work(작업자가 Work 에 저장) / final(검수자가 Final 에 저장)
    worker    : 저장한 사람 이름 (작업자든 검수자든, 역할은 work_type 으로 구분)

scene_type 은 TXT 에 들어가지 않으므로, 다음에 이미지를 열 때는
이 CSV 에서 '그 이미지의 가장 마지막 기록'을 찾아서 화면에 다시 보여줍니다.
"""

import csv
from datetime import datetime
from pathlib import Path

COLUMNS = ["file_name", "work_date", "work_type", "worker", "scene_type"]
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class LabelLog:
    def __init__(self, csv_path):
        self.path = Path(csv_path)
        self.ensure_file()

    def ensure_file(self):
        """label.csv 가 없거나 비어 있으면 머리줄(컬럼 이름)만 있는 파일을 만듭니다."""
        if self.path.exists() and self.path.stat().st_size > 0:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig: 엑셀로 열어도 한글 이름이 깨지지 않도록 맨 앞에 BOM 표시를 붙입니다.
        with open(self.path, "w", encoding="utf-8-sig", newline="") as f:
            csv.writer(f).writerow(COLUMNS)

    def read_all(self):
        """모든 기록을 dict 목록으로 읽습니다."""
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def latest_scene_types(self):
        """{파일명: 가장 마지막 scene_type} - 아래쪽(최근) 기록이 위쪽 기록을 덮어씁니다."""
        latest = {}
        for row in self.read_all():
            if row.get("file_name") and row.get("scene_type"):
                latest[row["file_name"]] = row["scene_type"]
        return latest

    def append(self, file_name, work_type, worker, scene_type, when=None):
        """
        기록 한 줄 추가. 추가한 줄(dict)을 돌려줍니다.
        ⚠ 엑셀로 label.csv 를 열어 둔 상태면 윈도우가 파일을 잠가서 PermissionError 가 납니다.
        """
        self.ensure_file()
        row = {
            "file_name": file_name,
            "work_date": (when or datetime.now()).strftime(DATE_FORMAT),
            "work_type": work_type,
            "worker": worker,
            "scene_type": scene_type,
        }
        # 이어쓰기("a")는 BOM 없이 utf-8 로! (utf-8-sig 로 이어쓰면 중간에 BOM 이 끼어듭니다)
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writerow(row)
        return row
