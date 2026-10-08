"""
라벨 통계 뽑기 (QA Summary · Handoff 보강용)

RAW(원본) 와 FINAL(최종) YOLO TXT 를 비교해서
교과 7 가이드 14장 '최종 데이터 품질 지표' 중 아직 보고서에 없는 숫자를 Markdown 으로 출력합니다.

사용법 (프로젝트 루트에서, 가상환경 켠 상태):
    python -m tools.label_stats --data data > reports/label_stats.md

※ 이 스크립트는 파일을 읽기만 합니다. RAW / WORK / FINAL 어디에도 쓰지 않습니다.
"""
import argparse
import csv
from collections import Counter
from pathlib import Path

CLASS_NAMES = {0: "나뭇잎·종이류", 1: "플라스틱류·돌·금속류", 2: "나뭇가지류", 3: "벌레류",
               4: "고무장갑 (미사용)", 5: "병해·갈변", 6: "파·고추"}
SCENE_NAMES = {"kimchi_with_target": "김치 + 검출 대상 객체", "normal_kimchi": "정상 김치",
               "object_only": "대상 객체 단독", "other_review": "분류 어려움"}


def read_labels(txt_path):
    """TXT 한 개를 읽어 class_id 리스트로 돌려줍니다. (형식 오류 줄은 Validation 에서 잡으므로 건너뜀)"""
    ids = []
    for line in txt_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 5:
            try:
                ids.append(int(float(parts[0])))
            except ValueError:
                pass
    return ids


def collect(paths):
    """{파일 기본이름: [class_id, ...]} 딕셔너리를 만듭니다."""
    return {p.stem: read_labels(p) for p in paths}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data", help="data 폴더 경로")
    ap.add_argument("--manifest", default="manifests/dataset_manifest.csv")
    a = ap.parse_args()
    data = Path(a.data)

    # 1) RAW / FINAL 파일 모으기 (raw 는 데이터셋 · split 폴더 구조 그대로)
    raw_imgs = {p.stem for p in (data / "raw").rglob("*.jpg")}
    raw = collect(p for p in (data / "raw").rglob("*.txt") if "labels" in p.parts)
    fin_imgs = {p.stem for p in (data / "final" / "images").glob("*.jpg")}
    fin = collect((data / "final" / "labels").glob("*.txt"))

    out = ["# 라벨 통계 (RAW vs FINAL)", "",
           "> `tools/label_stats.py` 로 생성. 파일을 읽기만 하며 원본은 바꾸지 않습니다.", ""]

    # 2) 최초 데이터 점검 (RAW Audit)
    out += ["## 1. RAW 최초 점검", "", "| 항목 | 값 |", "|---|---:|",
            f"| RAW 이미지 | {len(raw_imgs)} |", f"| RAW TXT | {len(raw)} |",
            f"| 이미지-TXT Pair 일치 | {len(raw_imgs & raw.keys())} |",
            f"| TXT 없는 이미지 | {len(raw_imgs - raw.keys())} |",
            f"| 이미지 없는 TXT | {len(raw.keys() - raw_imgs)} |",
            f"| Empty TXT (BBox 0개) | {sum(1 for v in raw.values() if not v)} |",
            f"| Class 4 포함 TXT | {sum(1 for v in raw.values() if 4 in v)} |", ""]

    # 3) Class 별 BBox 수
    rc = Counter(c for v in raw.values() for c in v)
    fc = Counter(c for v in fin.values() for c in v)
    out += ["## 2. Class 별 BBox 수", "", "| Class | 이름 | RAW | FINAL | 증감 |", "|:-:|---|---:|---:|---:|"]
    for cid in sorted(set(CLASS_NAMES) | rc.keys() | fc.keys()):
        out.append(f"| {cid} | {CLASS_NAMES.get(cid, '알 수 없음')} | {rc[cid]} | {fc[cid]} | {fc[cid] - rc[cid]:+d} |")
    out += [f"| | **합계** | **{sum(rc.values())}** | **{sum(fc.values())}** | **{sum(fc.values()) - sum(rc.values()):+d}** |", ""]

    # 4) 이미지 단위 변경 내역 (RAW 와 FINAL 비교)
    same = more = less = cls_changed = 0
    added = removed = 0
    for stem, f_ids in fin.items():
        r_ids = raw.get(stem, [])
        diff = len(f_ids) - len(r_ids)
        if diff > 0:
            more += 1; added += diff
        elif diff < 0:
            less += 1; removed -= diff
        if Counter(f_ids) != Counter(r_ids) and diff == 0:
            cls_changed += 1
        if Counter(f_ids) == Counter(r_ids) and diff == 0:
            same += 1
    out += ["## 3. 라벨 변경 내역 (이미지 기준)", "",
            "BBox 좌표만 조정한 경우는 여기서 '개수 · Class 동일'에 포함됩니다.", "",
            "| 항목 | 값 |", "|---|---:|",
            f"| FINAL 이미지 / TXT | {len(fin_imgs)} / {len(fin)} |",
            f"| BBox 개수 · Class 구성이 RAW 와 같은 이미지 | {same} |",
            f"| BBox 가 늘어난 이미지 (추가) | {more}장 · +{added}개 |",
            f"| BBox 가 줄어든 이미지 (삭제) | {less}장 · -{removed}개 |",
            f"| 개수는 같고 Class 구성이 바뀐 이미지 | {cls_changed} |",
            f"| FINAL Empty TXT | {sum(1 for v in fin.values() if not v)} |", ""]

    # 5) scene_type 별 수량 (manifest)
    mpath = Path(a.manifest)
    if mpath.exists():
        rows = list(csv.DictReader(mpath.open(encoding="utf-8-sig")))
        sc = Counter(r["scene_type"] for r in rows)
        out += ["## 4. scene_type 별 이미지 수", "", "| scene_type | 의미 | 이미지 수 |", "|---|---|---:|"]
        for k, name in SCENE_NAMES.items():
            out.append(f"| `{k}` | {name} | {sc.get(k, 0)} |")
        out.append("")

    print("\n".join(out))


if __name__ == "__main__":
    main()
