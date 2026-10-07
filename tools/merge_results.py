"""
merge_results.py - 팀원 5명의 작업 결과 합치기
==============================================

[왜 필요한가요?]
    900장 원본(data/raw)은 Git 에 올리지 않으니, 각자 자기 컴퓨터의 data 폴더에서 작업합니다.
    그러면 박건 님 컴퓨터에는 박건 님 작업만, 이승훈 님 컴퓨터에는 이승훈 님 작업만 남겠죠?
    이 도구는 '각자의 결과 묶음(zip)'을 하나의 data 폴더로 합쳐 줍니다.

    결과 묶음에는 원본 이미지가 들어가지 않습니다. (TXT · CSV 만 → 용량이 아주 작음)
        work/labels/*.txt         1차 검수 결과
        final/labels/*.txt        QA PASS 결과   (final/images 는 합칠 때 raw 에서 다시 복사)
        manifests/*.csv           작업대장 · 작업 이력

[같은 이미지를 두 사람이 고쳤다면?]
    label_history.csv 의 시간을 비교해서 '가장 나중에 한 작업'이 이깁니다. (Last write wins)
    충돌한 이미지 목록은 화면에 따로 보여 주니, 필요하면 프로그램에서 다시 확인하세요.

[사용법]  (프로젝트 폴더에서)
    # ① 각자: 내 결과 묶음 만들기
    python -m tools.merge_results pack --data ../data --out ../박건_1007.zip

    # ② 팀장: 받은 묶음을 내 data 폴더에 합치기 (먼저 --dry-run 으로 미리보기 추천)
    python -m tools.merge_results merge --data ../data ../박건_1007.zip ../이승훈_1007.zip --dry-run
    python -m tools.merge_results merge --data ../data ../박건_1007.zip ../이승훈_1007.zip

    # ③ 팀장: 합친 결과를 다시 pack 해서 팀원에게 → 팀원도 merge 하면 모두 같은 상태
"""

import argparse
import csv
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.records.history import COLUMNS as HISTORY_COLUMNS, History   # noqa: E402
from src.records.manifest import COLUMNS as MANIFEST_COLUMNS, QA_PASS, Manifest  # noqa: E402
from src.yolo.yolo_loader import STAGE_FINAL, STAGE_WORK, build_workspace  # noqa: E402
from src.yolo.yolo_writer import remove_from_final                    # noqa: E402

# 결과 묶음에 넣는 폴더 (원본 이미지 · final/images 는 넣지 않음)
PACK_DIRS = ("work/labels", "final/labels", "manifests")


# ==================================================
# 1. pack : 내 결과 묶음 만들기
# ==================================================

def pack(data_dir, out_path):
    data_dir, out_path = Path(data_dir), Path(out_path)
    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in PACK_DIRS:
            folder = data_dir / sub
            if not folder.is_dir():
                continue
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.suffix.lower() in (".txt", ".csv"):
                    zf.write(p, f"{sub}/{p.name}")
                    count += 1
    print(f"✔ 결과 묶음 {out_path}  (파일 {count}개, 원본 이미지는 들어가지 않음)")


# ==================================================
# 2. merge : 받은 묶음 합치기
# ==================================================

def _safe_extract(zip_path, dest):
    """묶음 안의 허용된 폴더(work/labels, final/labels, manifests)만 꺼냅니다. (이상한 경로는 무시)"""
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            parts = Path(name).parts
            if ".." in parts or name.startswith("/") or len(parts) < 2:
                continue
            if "/".join(parts[:-1]) not in PACK_DIRS:
                continue
            target = dest / Path(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _read_csv(path):
    if not path.is_file():
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _latest_by_file(history_rows):
    """{file_name: 가장 최근 work_date}"""
    latest = {}
    for r in history_rows:
        name, when = r.get("file_name", ""), r.get("work_date", "")
        if name and when > latest.get(name, ""):
            latest[name] = when
    return latest


class Source:
    """팀원 한 명의 결과 묶음 (zip 또는 폴더)"""

    def __init__(self, path, tmp_root):
        self.path = Path(path)
        self.name = self.path.stem
        if self.path.is_file() and zipfile.is_zipfile(self.path):
            self.root = Path(tempfile.mkdtemp(dir=tmp_root))
            _safe_extract(self.path, self.root)
        elif self.path.is_dir():
            self.root = self.path
        else:
            raise FileNotFoundError(f"zip 또는 data 폴더가 아닙니다: {self.path}")
        self.history = _read_csv(self.root / "manifests" / "label_history.csv")
        self.rows = {r["file_name"]: r for r in _read_csv(self.root / "manifests" / "dataset_manifest.csv")}
        self.latest = _latest_by_file(self.history)
        self.events = {}                    # {file_name: {(시간, 작업, 사람), ...}}  충돌 판단용
        for r in self.history:
            self.events.setdefault(r.get("file_name", ""), set()).add(
                (r.get("work_date", ""), r.get("action", ""), r.get("user", "")))

    def last_event(self, name):
        return next((e for e in self.events.get(name, ()) if e[0] == self.latest.get(name)), None)

    def label_file(self, item, qa_status):
        sub = "final" if qa_status == QA_PASS else "work"
        return self.root / sub / "labels" / item.label_name


def merge(data_dir, sources, dry_run=False):
    ws = build_workspace(data_dir)
    if not ws.items:
        sys.exit(f"이미지가 없습니다: {data_dir}  (data/raw/ 에 원본 데이터셋이 있어야 합니다)")
    items = {it.key: it for it in ws.items}
    manifest = Manifest(ws.manifest_path, ws.items)
    history = History(ws.history_path)
    master_rows = history.read_all()
    master_latest = _latest_by_file(master_rows)

    with tempfile.TemporaryDirectory() as tmp:
        srcs = [Source(s, tmp) for s in sources]

        # --- 이미지마다 '가장 최근 작업'을 가진 쪽 찾기 ---
        plan, conflicts, unknown = [], [], set()
        names = set().union(*(s.latest for s in srcs)) if srcs else set()
        for name in sorted(names):
            if name not in items:
                unknown.add(name)
                continue
            candidates = [(s.latest[name], s) for s in srcs if name in s.latest and name in s.rows]
            when, best = max(candidates, key=lambda c: c[0])
            # 진짜 충돌 = 다른 사람의 마지막 작업을 이긴 쪽이 '모르는' 경우
            #   (B 가 A 의 결과를 이미 합친 뒤 이어서 작업했다면 B 이력에 A 의 작업이 있으므로 충돌 아님)
            lost = {s.name for w, s in candidates
                    if s is not best and w > master_latest.get(name, "")
                    and s.last_event(name) not in best.events.get(name, ())}
            if lost:
                conflicts.append((name, sorted(lost | {best.name}), best.name))
            if when > master_latest.get(name, ""):
                plan.append((name, best, when))

        print(f"합칠 묶음 {len(srcs)}개 → 바뀔 이미지 {len(plan)}장"
              + (f" · 충돌 {len(conflicts)}장 (최신 작업 우선)" if conflicts else ""))
        for name, by, winner in conflicts:
            print(f"  ⚠ 충돌 {name}: {', '.join(by)} 가 모두 수정 → {winner} 의 결과 사용")
        if unknown:
            print(f"  ⚠ 내 data/raw 에 없는 이미지 {len(unknown)}장은 건너뜀 (예: {sorted(unknown)[:3]})")

        applied, missing = 0, []
        for name, src, when in plan:
            row = src.rows[name]
            item = items[name]
            label = src.label_file(item, row.get("qa_status"))
            if not label.is_file():
                missing.append(f"{name} ({src.name})")
                continue
            line = (f"  {name}: {row.get('status') or '-'} / {row.get('qa_status') or '-'}"
                    f"  ← {src.name} ({when})")
            print(line)
            if dry_run:
                continue
            _apply(item, row, label)
            manifest.rows[name].update({c: (row.get(c) or "") for c in MANIFEST_COLUMNS
                                        if c not in ("file_name", "source_dataset", "original_split")})
            applied += 1
        if missing:
            print(f"  ⚠ TXT 가 묶음에 없어 건너뜀 {len(missing)}장: {missing[:5]}")

        if dry_run:
            print("(미리보기 --dry-run : 아무것도 바꾸지 않았습니다)")
            return
        manifest.save()

        # --- 작업 이력은 모두 모으기 (같은 줄은 한 번만) ---
        seen = {tuple(r.get(c, "") for c in HISTORY_COLUMNS) for r in master_rows}
        new_rows = []
        for s in srcs:
            for r in s.history:
                key = tuple(r.get(c, "") for c in HISTORY_COLUMNS)
                if key not in seen and r.get("file_name") in items:
                    seen.add(key)
                    new_rows.append(r)
        for r in sorted(new_rows, key=lambda r: r.get("work_date", "")):
            history.append(**{c: r.get(c, "") for c in HISTORY_COLUMNS})
        print(f"✔ 합치기 완료: 이미지 {applied}장 갱신 · 작업 이력 {len(new_rows)}줄 추가 "
              f"({datetime.now():%Y-%m-%d %H:%M})")
        print("  → 프로그램에서 F7(Validation) 또는  python -m tools.make_reports --data ... 로 확인하세요.")


def _apply(item, row, label_src):
    """한 이미지의 결과를 내 data 폴더에 반영 (raw 는 건드리지 않음)"""
    if row.get("qa_status") == QA_PASS:
        dst = item.label_path(STAGE_FINAL)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(label_src, dst)
        img = item.final_image_path
        img.parent.mkdir(parents=True, exist_ok=True)
        if not img.exists():
            shutil.copy2(item.path, img)                    # 이미지는 내 raw 에서 복사
        work = item.label_path(STAGE_WORK)
        if work.is_file():
            work.unlink()
    else:
        dst = item.label_path(STAGE_WORK)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(label_src, dst)
        remove_from_final(item)                             # QA 대기로 돌아갔으면 final 에서 빼기


# ==================================================
# 3. 명령어
# ==================================================

def main():
    parser = argparse.ArgumentParser(description="팀원 작업 결과 묶기(pack) / 합치기(merge)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="내 결과 묶음(zip) 만들기")
    p.add_argument("--data", required=True, help="내 data 폴더")
    p.add_argument("--out", required=True, help="만들 zip 파일 (예: ../박건_1007.zip)")
    m = sub.add_parser("merge", help="받은 묶음을 내 data 폴더에 합치기")
    m.add_argument("--data", required=True, help="합칠 대상 data 폴더 (raw 가 있어야 함)")
    m.add_argument("sources", nargs="+", help="팀원 결과 zip 또는 data 폴더")
    m.add_argument("--dry-run", action="store_true", help="바뀔 내용만 미리 보기")
    args = parser.parse_args()
    if args.cmd == "pack":
        pack(args.data, args.out)
    else:
        merge(args.data, args.sources, args.dry_run)


if __name__ == "__main__":
    main()
