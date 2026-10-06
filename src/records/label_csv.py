"""
label_csv.py - 통합 라벨 작업 기록 (data/labels/label.csv)
=========================================================

저장할 때마다 한 줄씩 덧붙이는 '작업 일지'입니다. (지금까지의 기록은 지우지 않음)

    file_name,work_date,work_type,worker,scene_type,source_dataset,original_split,qa_status
    a.jpg,2026-10-07 10:12:05,work,박건,kimchi_with_target,dataset1,train,PASS
    a.jpg,2026-10-07 11:30:41,final,최용훈,kimchi_with_target,dataset1,train,PASS
    c.jpg,2026-10-07 11:40:02,work,이승훈,normal_kimchi,dataset2,validation,WAIT

    work_type      : work(작업자가 Work 에 저장) / final(검수자가 Final 에 저장)
    worker         : 저장한 사람 이름
    source_dataset : 원래 어느 데이터셋에서 왔는지 (dataset1, dataset2)
    original_split : 기존 train / validation 위치
    qa_status      : QA 완료 여부  →  Work 에 저장되면 WAIT, Final 로 이동하면 PASS

[qa_status 규칙]
    qa_status 는 '이 이미지의 지금 상태'입니다.
    저장할 때마다 같은 이미지의 모든 줄을 최신 상태로 맞춥니다.
        → work 줄이 남아 있어도 Final 로 가면 그 이미지 줄은 전부 PASS
        → 엑셀에서 qa_status = WAIT 로 거르면 '아직 검수 안 된 이미지'만 남습니다.

scene_type 은 TXT 에 들어가지 않으므로, 다음에 이미지를 열 때는
이 CSV 에서 '그 이미지의 가장 마지막 기록'을 찾아서 화면에 다시 보여줍니다.
"""

import csv
import os
from datetime import datetime
from pathlib import Path

COLUMNS = ["file_name", "work_date", "work_type", "worker", "scene_type",
           "source_dataset", "original_split", "qa_status"]
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

QA_WAIT = "WAIT"
QA_PASS = "PASS"
QA_BY_WORK_TYPE = {"work": QA_WAIT, "final": QA_PASS}


class LabelLog:
    def __init__(self, csv_path):
        self.path = Path(csv_path)
        self.migrated_from = None        # 예전 형식에서 바꿨으면 백업 파일 경로
        self.ensure_file()

    # ---------- 파일 준비 ----------
    def ensure_file(self):
        """
        label.csv 가 없으면 머리줄만 있는 파일을 만들고,
        예전 형식(컬럼이 적은 파일)이면 백업해 두고 새 형식으로 바꿉니다.
        """
        if not self.path.exists() or self.path.stat().st_size == 0:
            self._write_all([])
            return
        with open(self.path, "r", encoding="utf-8-sig", newline="") as f:
            header = next(csv.reader(f), [])
        if header != COLUMNS:
            self._migrate()

    def _migrate(self):
        """예전 label.csv (v2.x, 5개 컬럼) → 새 형식. 원래 파일은 label_backup_날짜.csv 로 남김"""
        old_rows = self.read_all()
        backup = self.path.with_name(f"label_backup_{datetime.now():%Y%m%d_%H%M%S}.csv")
        os.replace(self.path, backup)
        rows = []
        for r in old_rows:
            name = r.get("file_name", "")
            split = r.get("original_split", "")
            if "/" in name:                      # v2.x 는 'train/a.jpg' 처럼 적었음
                split = split or name.rsplit("/", 1)[0]
                name = name.rsplit("/", 1)[1]
            row = {c: r.get(c, "") for c in COLUMNS}
            row.update(file_name=name, original_split=split)
            row["qa_status"] = row["qa_status"] or QA_BY_WORK_TYPE.get(row["work_type"], QA_WAIT)
            rows.append(row)
        self._sync_status(rows)
        self._write_all(rows)
        self.migrated_from = backup

    def _write_all(self, rows):
        """
        파일 전체를 다시 씁니다. 임시 파일에 먼저 쓰고 한 번에 바꿔치기(os.replace)
        → 쓰는 도중 꺼져도 label.csv 가 반쪽짜리가 되지 않습니다.
        utf-8-sig: 엑셀로 열어도 한글이 깨지지 않게 맨 앞에 BOM 표시
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".csv.tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, self.path)

    # ---------- 읽기 ----------
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

    def qa_summary(self):
        """{'WAIT': n, 'PASS': m}  (이미지 기준 개수)"""
        status = {}
        for row in self.read_all():
            if row.get("file_name"):
                status[row["file_name"]] = row.get("qa_status", "")
        return {s: list(status.values()).count(s) for s in (QA_WAIT, QA_PASS)}

    # ---------- 쓰기 ----------
    def backfill_origin(self, origin):
        """
        source_dataset / original_split 이 빈 줄을 채웁니다. (예전 형식에서 바꾼 줄)
        origin: {file_name: (source_dataset, original_split)}
        돌려주는 값: 채운 줄 수
        """
        rows = [{c: r.get(c, "") for c in COLUMNS} for r in self.read_all()]
        filled = 0
        for r in rows:
            if r["file_name"] in origin and not (r["source_dataset"] and r["original_split"]):
                src, split = origin[r["file_name"]]
                r["source_dataset"] = r["source_dataset"] or src
                r["original_split"] = r["original_split"] or split
                filled += 1
        if filled:
            self._write_all(rows)
        return filled

    @staticmethod
    def _sync_status(rows):
        """같은 이미지의 모든 줄을 '가장 마지막 줄'의 qa_status 로 맞춥니다."""
        latest = {r["file_name"]: r["qa_status"] for r in rows}
        for r in rows:
            r["qa_status"] = latest[r["file_name"]]

    def append(self, file_name, work_type, worker, scene_type,
               source_dataset="", original_split="", when=None):
        """
        기록 한 줄 추가 + 같은 이미지의 qa_status 를 최신으로 갱신. 추가한 줄(dict)을 돌려줍니다.
        ⚠ 엑셀로 label.csv 를 열어 둔 상태면 윈도우가 파일을 잠가서 PermissionError 가 납니다.
        """
        self.ensure_file()
        row = {
            "file_name": file_name,
            "work_date": (when or datetime.now()).strftime(DATE_FORMAT),
            "work_type": work_type,
            "worker": worker,
            "scene_type": scene_type,
            "source_dataset": source_dataset,
            "original_split": original_split,
            "qa_status": QA_BY_WORK_TYPE.get(work_type, QA_WAIT),
        }
        rows = [{c: r.get(c, "") for c in COLUMNS} for r in self.read_all()]
        rows.append(row)
        self._sync_status(rows)
        self._write_all(rows)
        return row
