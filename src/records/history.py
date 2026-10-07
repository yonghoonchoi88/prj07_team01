"""
history.py - 작업 이력 (manifests/label_history.csv)
===================================================

manifest 는 '지금 상태'만 남기므로, '누가 · 언제 · 무엇을' 했는지는 여기에 계속 쌓습니다.
(지우거나 고치지 않는 작업 일지)  → QA Summary 의 Human QA 숫자를 계산할 때 씁니다.

    work_date,file_name,action,user,role,status,qa_status,review_reason,scene_type,bbox_count
    2026-10-07 10:12:05,a.jpg,work_save,박건,worker,EDITED,WAIT,,kimchi_with_target,3
    2026-10-07 11:30:41,a.jpg,qa_pass,최용훈,reviewer,EDITED,PASS,,kimchi_with_target,3

    action : work_save (1차 검수 저장) / qa_pass (QA PASS → final) / qa_reject (검수자 반려 → REVIEW)
"""

import csv
from datetime import datetime
from pathlib import Path

COLUMNS = ["work_date", "file_name", "action", "user", "role", "status",
           "qa_status", "review_reason", "scene_type", "bbox_count"]
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

ACTION_WORK = "work_save"
ACTION_PASS = "qa_pass"
ACTION_REJECT = "qa_reject"


class History:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file() or self.path.stat().st_size == 0:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerow(COLUMNS)

    def append(self, **fields):
        row = {c: "" for c in COLUMNS}
        row.update({k: ("" if v is None else str(v)) for k, v in fields.items()})
        row["work_date"] = row["work_date"] or datetime.now().strftime(DATE_FORMAT)
        # 이어쓰기는 BOM 없이 utf-8 로! (utf-8-sig 로 이어쓰면 중간에 BOM 이 끼어듭니다)
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            csv.DictWriter(f, fieldnames=COLUMNS).writerow(row)
        return row

    def read_all(self):
        if not self.path.is_file():
            return []
        with open(self.path, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
