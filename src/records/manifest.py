"""
manifest.py - Dataset Manifest (manifests/dataset_manifest.csv)
==============================================================

교과7 7번 산출물. 900장의 이미지가 '지금' 어떤 상태인지 한눈에 보는 작업대장입니다.
이미지 1장 = 1줄 (저장할 때마다 줄이 늘어나는 게 아니라, 그 이미지의 줄이 갱신됩니다)

    file_name,source_dataset,original_split,scene_type,worker,status,qa_status,review_reason
    250410_144403911987.jpg,dataset2,train,kimchi_with_target,박건,DONE,PASS,
    250410_144405445566.jpg,dataset1,train,object_only,이승훈,REVIEW,WAIT,class_ambiguous

    status        : DONE   (원본 라벨이 맞아서 수정 없이 검수 완료)
                    EDITED (원본 라벨을 수정 · 추가 · 삭제한 뒤 저장)
                    REVIEW (판단이 어려워 추가 검수가 필요)  → review_reason 필수
                    (빈칸) 아직 1차 검수 전
    qa_status     : PASS (최종 검수 완료 = final 에 있음) / WAIT (아직 QA 전)
    worker        : 1차 검수 작업자

'누가 언제 무엇을 했는지'는 label_history.csv (history.py) 에 따로 쌓입니다.
"""

import csv
import os
from pathlib import Path

COLUMNS = ["file_name", "source_dataset", "original_split", "scene_type",
           "worker", "status", "qa_status", "review_reason"]

STATUS_DONE = "DONE"
STATUS_EDITED = "EDITED"
STATUS_REVIEW = "REVIEW"
STATUSES = (STATUS_DONE, STATUS_EDITED, STATUS_REVIEW)
QA_PASS = "PASS"
QA_WAIT = "WAIT"


class Manifest:
    def __init__(self, path, items):
        """
        path  : manifests/dataset_manifest.csv
        items : 작업 공간의 이미지 목록 → 없는 이미지 줄은 새로 만들고, 출처 정보는 항상 최신으로 맞춤
        """
        self.path = Path(path)
        self.rows = {}                      # {file_name: {컬럼: 값}}  (이미지 순서 유지)
        old = self._read()
        for it in items:
            row = {c: "" for c in COLUMNS}
            row.update(old.pop(it.key, {}))
            row.update(file_name=it.key, source_dataset=it.source_dataset,
                       original_split=it.original_split)
            row["qa_status"] = row["qa_status"] or QA_WAIT
            self.rows[it.key] = row
        self.orphans = old                  # manifest 에는 있는데 이미지가 없는 줄 (Validation 에서 보고)
        self.rows.update(old)               # 지우지 않고 뒤에 남겨 둠
        self.save()

    # ---------- 읽기 / 쓰기 ----------
    def _read(self):
        if not self.path.is_file():
            return {}
        with open(self.path, "r", encoding="utf-8-sig", newline="") as f:
            return {r["file_name"]: {c: (r.get(c) or "").strip() for c in COLUMNS}
                    for r in csv.DictReader(f) if r.get("file_name")}

    def save(self):
        """
        전체를 다시 씁니다. 임시 파일에 쓰고 한 번에 바꿔치기 → 반쪽 파일이 남지 않음
        utf-8-sig : 엑셀로 열어도 한글이 깨지지 않음
        ⚠ 엑셀로 열어 둔 상태면 윈도우가 파일을 잠가서 PermissionError 가 납니다.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".csv.tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(self.rows.values())
        os.replace(tmp, self.path)

    def get(self, file_name):
        return self.rows.get(file_name, {c: "" for c in COLUMNS})

    def update(self, file_name, **fields):
        """한 이미지의 줄을 갱신하고 바로 저장. 바꾸기 전 값을 돌려줍니다. (저장 실패 시 되돌리기용)"""
        before = dict(self.rows[file_name])
        self.rows[file_name].update({k: ("" if v is None else str(v)) for k, v in fields.items()})
        try:
            self.save()
        except OSError:
            self.rows[file_name] = before            # 파일에 못 썼으면 메모리도 원래대로
            raise
        return before

    # ---------- 집계 ----------
    def image_rows(self):
        """실제 이미지가 있는 줄만 (orphan 제외)"""
        return [r for k, r in self.rows.items() if k not in self.orphans]

    def counts(self):
        rows = self.image_rows()
        return {
            "total": len(rows),
            "PASS": sum(r["qa_status"] == QA_PASS for r in rows),
            "REVIEW": sum(r["status"] == STATUS_REVIEW for r in rows),
            "DONE": sum(r["status"] == STATUS_DONE for r in rows),
            "EDITED": sum(r["status"] == STATUS_EDITED for r in rows),
            "TODO": sum(not r["status"] for r in rows),
            "WAIT_QA": sum(r["status"] in (STATUS_DONE, STATUS_EDITED) and r["qa_status"] != QA_PASS
                           for r in rows),
        }
