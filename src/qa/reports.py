"""
reports.py - 산출물 자동 생성 (교과7 7 · 8 · 9 · 11번)
=====================================================

    manifests/dataset_manifest.csv   7번  Dataset Manifest  (data 의 작업대장을 프로젝트로 복사)
    reports/qa_summary.md            8번  QA Summary        (자동 Validation + Human QA 숫자)
    reports/validation_report.csv         이미지별 Validation 상세
    reports/test_report.md           9번  Test Report       (Golden / Pilot / Final Acceptance)
    docs/subject08_handoff.md        11번 교과 8 Handoff

[자동 영역 표시]
    <!-- AUTO:이름:START --> ... <!-- AUTO:이름:END --> 사이만 프로그램이 다시 씁니다.
    그 밖에 팀이 직접 적은 내용(FAIL 기록, 메모 등)은 다시 생성해도 지워지지 않습니다.
"""

import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.records.history import ACTION_REJECT
from src.records.manifest import QA_PASS, STATUS_REVIEW
from src.validation.validator import ERROR_TYPES, read_runs, write_report_csv

CRITICAL_TYPES = ("pair", "format")          # 저장 · Pair 가 깨지는 치명적 오류


# ==================================================
# 0. 자동 영역 갱신
# ==================================================

def _block(name, body):
    return f"<!-- AUTO:{name}:START -->\n{body.rstrip()}\n<!-- AUTO:{name}:END -->"


def write_marked(path, blocks, template):
    """
    path 가 없으면 template 으로 새로 만들고, 있으면 AUTO 영역만 교체합니다.
    template 안에는 {이름} 자리에 자동 영역이 들어갑니다.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(template.format(**{k: _block(k, v) for k, v in blocks.items()}), encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    for name, body in blocks.items():
        pattern = re.compile(rf"<!-- AUTO:{name}:START -->.*?<!-- AUTO:{name}:END -->", re.S)
        if pattern.search(text):
            text = pattern.sub(lambda _: _block(name, body), text)
        else:
            text = text.rstrip() + "\n\n" + _block(name, body) + "\n"
    path.write_text(text, encoding="utf-8")


def _pct(a, b):
    return f"{a / b * 100:.1f}%" if b else "-"


# ==================================================
# 1. 7번 Dataset Manifest
# ==================================================

def export_manifest(ws, project_dir):
    dst = Path(project_dir) / "manifests" / "dataset_manifest.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ws.manifest_path, dst)
    return dst


# ==================================================
# 2. 8번 QA Summary
# ==================================================

def qa_numbers(ws, manifest, history_rows, result, runs):
    """QA Summary · Acceptance · Handoff 가 같이 쓰는 숫자 모음"""
    rows = manifest.image_rows()
    total = len(rows)
    c = manifest.counts()
    final_labels = {p.stem for p in (ws.final_dir / "labels").glob("*.txt")}
    final_images = {p.stem for p in (ws.final_dir / "images").glob("*") if p.is_file()}
    first, last = (runs[0], runs[-1]) if runs else (None, None)
    first_failed = set(first["failed_files"].split(";")) - {""} if first else set()
    ever_review = {h["file_name"] for h in history_rows if h["status"] == STATUS_REVIEW}
    rejected = {h["file_name"] for h in history_rows if h["action"] == ACTION_REJECT}
    targets = first_failed | ever_review
    failing_now = {r["file_name"] for r in result.failed}
    pass_now = {r["file_name"] for r in rows if r["qa_status"] == QA_PASS}
    resolved = {f for f in targets if f in pass_now and f not in failing_now}
    by_type = result.by_type()
    return {
        "total": total, "counts": c,
        "final_labels": len(final_labels), "final_images": len(final_images),
        "final_pairs": len(final_labels & final_images),
        "first": first, "last": last, "runs": len(runs),
        "targets": len(targets), "resolved": len(resolved), "unresolved": len(targets - resolved),
        "rejected": len(rejected), "ever_review": len(ever_review),
        "fail_now": result.fail_count, "pass_now_valid": len(pass_now - failing_now),
        "critical": sum(by_type[k] for k in CRITICAL_TYPES), "by_type": by_type,
        "reasons_now": Counter(r["review_reason"] for r in rows if r["status"] == STATUS_REVIEW),
        "reasons_ever": Counter(h["review_reason"] for h in history_rows
                                if h["status"] == STATUS_REVIEW and h["review_reason"]),
        "origin": Counter((r["source_dataset"], r["original_split"]) for r in rows),
    }


def qa_summary_blocks(ws, n, reasons):
    c = n["counts"]
    total = n["total"]
    origin = "\n".join(f"| {d or '-'} | {s or '-'} | {k} |" for (d, s), k in sorted(n["origin"].items()))
    first, last = n["first"], n["last"]

    def run_line(run):
        if not run:
            return "- (아직 실행하지 않음)"
        return f"- 실행 시각: {run['run_at']}\n- PASS: {run['pass']}장\n- FAIL: {run['fail']}건"

    type_rows = "\n".join(
        f"| {name} | {first[k] if first else '-'} | {n['by_type'][k]} |" for k, name in ERROR_TYPES.items())
    first_total = sum(int(first[k]) for k in ERROR_TYPES) if first else 0
    reason_rows = "\n".join(
        f"| `{k}` | {desc} | {n['reasons_ever'].get(k, 0)} | {n['reasons_now'].get(k, 0)} |"
        for k, desc in reasons.items())

    review_now = c["REVIEW"]
    done = n["pass_now_valid"] == total and n["fail_now"] == 0 and review_now == 0 and total > 0
    verdict = "QA 완료" if done else "진행 중"
    why = [] if done else [t for t, bad in (
        (f"QA PASS 미완료 {total - c['PASS']}장", c["PASS"] < total),
        (f"Validation FAIL {n['fail_now']}건", n["fail_now"] > 0),
        (f"미해결 REVIEW {review_now}장", review_now > 0)) if bad]

    return {
        "DATA": f"""## 1. 전체 데이터

- 전체 이미지: {total}장
- FINAL 이미지: {n['final_images']}장 / FINAL TXT: {n['final_labels']}개 (이미지-TXT Pair 일치 {n['final_pairs']}쌍)
- 1차 검수 완료: {total - c['TODO']}장 / {total}장 (DONE {c['DONE']} · EDITED {c['EDITED']} · REVIEW {c['REVIEW']})
- 라벨 검수 완료 (QA PASS): {c['PASS']}장 / {total}장 ({_pct(c['PASS'], total)})

| source_dataset | original_split | 이미지 수 |
|---|---|---:|
{origin}
""",
        "VALIDATION": f"""## 2. 자동 Validation 결과

Validation 실행 횟수: {n['runs']}회 (manifests/validation_runs.csv)

### 최초 실행
{run_line(first)}

### 최종 실행
{run_line(last)}

### 발견된 오류 (이미지 수 기준)

| 오류 종류 | 최초 실행 | 최종 실행 |
|---|---:|---:|
{type_rows}

최초 실행 총 오류: {first_total}건  →  최종 실행 총 오류: {sum(n['by_type'].values())}건

상세 목록: `reports/validation_report.csv`
""",
        "HUMAN": f"""## 3. Human QA 결과

자동 Validation 에서 발견된 이미지와, 작업 중 REVIEW 로 올라온 이미지를 사람이 다시 확인했습니다.

- 검토 대상: {n['targets']}건 (최초 Validation FAIL + REVIEW 제기)
- 수정 완료: {n['resolved']}건
- 미해결: {n['unresolved']}건
- 교차검수 반려 (검수자 → REVIEW): {n['rejected']}건

### 1차 검수 상태 (현재)

| status | 의미 | 이미지 수 |
|---|---|---:|
| DONE | 기존 라벨이 맞아서 수정 없이 검수 완료 | {c['DONE']} |
| EDITED | 기존 라벨을 수정 · 추가 · 삭제한 뒤 저장 | {c['EDITED']} |
| REVIEW | 판단이 어려워 추가 검수 필요 | {c['REVIEW']} |
| (미작업) | 아직 1차 검수 전 | {c['TODO']} |

### REVIEW 사유

| review_reason | 의미 | 제기된 이미지 | 현재 미해결 |
|---|---|---:|---:|
{reason_rows}
""",
        "FINAL": f"""## 4. 최종 결과

- PASS: {n['pass_now_valid']}장
- FAIL: {n['fail_now']}장
- REVIEW: {review_now}장

최종 판정: **{verdict}**{'' if done else '  (' + ' · '.join(why) + ')'}

_자동 생성: {datetime.now():%Y-%m-%d %H:%M} · 데이터: `{ws.root}`_
""",
    }


QA_TEMPLATE = """# QA Summary

조각김치 이물검출 라벨 900장의 품질검사 결과입니다.
아래 숫자는 라벨링 프로그램의 **검사 → 산출물 생성** 으로 자동 갱신됩니다.

{DATA}

---

{VALIDATION}

---

{HUMAN}

---

{FINAL}

---

## 5. 메모 (직접 작성)

- 예) Empty TXT 4건은 이미지 확인 결과 정상 김치 → scene_type normal_kimchi 로 수정 후 PASS
"""


# ==================================================
# 3. 9번 Test Report
# ==================================================

def _test_block(title, purpose, t):
    if not t:
        return f"## {title}\n\n(아직 실행하지 않음 — 프로그램 메뉴 **검사 → Golden / Pilot 테스트 실행**)\n"
    rows = "\n".join(f"| {name} | {'PASS' if ok == t['n'] else 'FAIL'} ({ok}/{t['n']}) |"
                     for name, ok in t["per_test"].items())
    fails = "\n".join(f"- `{f}` · {test} · {memo}" for f, test, memo in t["fails"][:30]) or "- 없음"
    notes = "\n".join(f"- `{f}` · {memo}" for f, memo in t["notes"][:15])
    notes_part = ("\n\n### 데이터 확인 필요 (프로그램 오류 아님 → QA Summary 에서 처리)\n\n" + notes) if notes else ""
    return f"""## {title}

### 테스트 목적
{purpose}

### 테스트 데이터
- 실제 조각김치 이미지: {t['n']}장 (데이터셋 · split 이 고루 섞이도록 간격을 두고 선택)
- 실제 YOLO TXT: 대응하는 {t['n']}개 (원본은 바꾸지 않고 임시 폴더에서 저장 · Reload)
- 실행 시각: {t['run_at']} · 소요 {t['seconds']}초

### 테스트 결과

| 테스트 항목 | 결과 |
|---|---|
{rows}

최종 결과: {t['image_pass']} / {t['n']} PASS

### 실패 항목
{fails}{notes_part}
"""


def acceptance_block(n, golden, pilot):
    reload_ok = all(t and t["per_test"]["저장 후 Reload"] == t["n"] for t in (golden, pilot))
    c = n["counts"]
    total = n["total"]
    checks = [
        (f"{total}장 이미지 탐색 가능", total > 0),
        ("이미지와 TXT Pair 정상 (FINAL)", n["final_pairs"] == total and total > 0),
        ("저장 후 Reload 정상 (Golden · Pilot)", reload_ok),
        ("미처리 REVIEW 없음", c["REVIEW"] == 0),
        ("Critical Error 없음", n["critical"] == 0),
        ("Validation 오류 없음", n["fail_now"] == 0),
        (f"{total}장 전체 QA PASS", c["PASS"] == total and total > 0),
    ]
    rows = "\n".join(f"| {name} | {'PASS' if ok else 'NOT YET'} |" for name, ok in checks)
    accepted = all(ok for _, ok in checks)
    return f"""## 3. Final Acceptance Test

### 테스트 목적
900장 전체 검수 작업이 끝난 뒤 프로그램과 FINAL 데이터가 최종 사용 가능한 상태인지 확인합니다.

### 확인 항목

| 확인 항목 | 결과 |
|---|---|
{rows}

### 최종 결과

- 전체 대상: {total}장
- Critical Error: {n['critical']}건
- Unresolved Review: {c['REVIEW']}건
- Validation Error: {n['fail_now']}건

최종 판정: **{'ACCEPTED' if accepted else 'NOT YET'}**
"""


TEST_TEMPLATE = """# Labeling Tool Test Report

기능 검증은 `기능 확인 → 1장 End-to-End → Golden Sample → Pilot Test → 전체 Validation → Acceptance Test`
순서로 확대합니다. 숫자 영역은 프로그램이 자동으로 갱신하고, FAIL 기록은 팀이 직접 적습니다.

{GOLDEN}

---

{PILOT}

### Pilot 중 발견된 문제 (직접 작성)

> 처음부터 전부 PASS 일 필요는 없습니다. **문제 → 원인 → 조치 → 재시험** 을 남기는 것이 중요합니다.

#### FAIL-01 (개발 중 실제로 발견 · v2.1 에서 수정)
- 문제: 검수자가 RAW 원본만 있는 이미지를 1차 검수 없이 바로 FINAL 로 저장할 수 있었음
- 원인: FINAL 저장 시 work(1차 검수 결과)가 있는지 확인하지 않음
- 조치: 화면과 저장 함수 두 곳에서 work 존재 여부 확인 (이중 안전장치)
- 재시험: PASS

#### FAIL-02
- 문제:
- 원인:
- 조치:
- 재시험:

---

{ACCEPTANCE}
"""


# ==================================================
# 4. 11번 교과 8 Handoff
# ==================================================

def handoff_block(ws, n, classes):
    c = n["counts"]
    class_lines = "\n".join(
        f"- Class {k['id']}: {k['name']}" + ("" if k["enabled"] else " — 현재 사용하지 않음") for k in classes)
    sample = sorted((ws.final_dir / "labels").glob("*.txt"))[:1]
    example = (f"{sample[0].stem}.jpg\n{sample[0].stem}.txt" if sample
               else "250410_144403911987.jpg\n250410_144403911987.txt")
    origin = "\n".join(f"- {d or '-'} / {s or '-'}: {k}장" for (d, s), k in sorted(n["origin"].items()))
    return f"""## 2. FINAL Dataset

- 전체 이미지: {n['total']}장
- FINAL Image: {n['final_images']}장
- FINAL Label: {n['final_labels']}개
- Label Format: YOLO Detection TXT
- 이미지와 TXT 파일명 Pair: {n['final_pairs']}쌍 일치

FINAL 데이터 위치 (Git 에 올리지 않음):

```
data/final/
├── images/
└── labels/
```

예:

```
{example}
```

## 3. YOLO Label Format

TXT 한 줄은 객체 하나를 의미합니다.

```
class_id x_center y_center width height
```

좌표값은 이미지 크기 대비 0~1 범위의 정규화 좌표입니다.

## 4. Class 정보

{class_lines}

- 상세 Class 기준: `docs/class_guide.md`
- 프로그램 Class 설정: `configs/classes.yaml`

## 5. BBox 기준

BBox는 객체 외곽에 최대한 밀착하여 작성했습니다. 상세 기준: `docs/bbox_guide.md`

## 6. QA 결과

- Validation PASS: {n['pass_now_valid']}장
- FAIL: {n['fail_now']}장
- REVIEW: {c['REVIEW']}장
- Critical Error: {n['critical']}건

상세 QA 결과: `reports/qa_summary.md` · 프로그램 테스트 결과: `reports/test_report.md`

## 7. Dataset 작업 이력

`manifests/dataset_manifest.csv` 에서 원본 출처 · 기존 Split · 작업자 · 작업 상태 · QA 상태 · REVIEW 사유를 확인합니다.

기존 Split 분포:

{origin}
"""


HANDOFF_TEMPLATE = """# Subject 07 → Subject 08 Handoff

## 1. Handoff 목적

교과 7에서 검수 완료한 조각김치 이물검출 YOLO Dataset을
교과 8 Object Detection 학습에서 사용할 수 있도록 전달합니다.

{HANDOFF}

## 8. 교과 8 전달 자료

```
handoff_subject08/
├── final_dataset/
│   ├── images/
│   └── labels/
├── dataset_manifest.csv
├── class_guide.md
├── bbox_guide.md
└── subject08_handoff.md
```

※ 실제 900장 데이터는 GitHub에 올리지 않고 내부 저장소 또는 지정된 교육환경에서 전달합니다.
(라벨링 프로그램 메뉴 **검사 → 교과 8 Handoff 패키지 만들기** 로 위 폴더를 만들 수 있습니다)

## 9. 교과 8에서 확인할 내용

1. 이미지와 TXT Pair가 정상인지 확인
2. Class 0~6 설정 확인
3. Class 4 사용 여부 확인
4. YOLO TXT 형식 확인
5. 기존 Dataset Split 정보 확인
6. 학습용 Dataset 설정 파일 구성
7. YOLO Object Detection 학습 진행
"""


def make_handoff_package(ws, project_dir, out_dir):
    """handoff_subject08/ 폴더 만들기 (final 데이터 복사 + 문서). 돌려주는 값: 폴더 경로"""
    out = Path(out_dir)
    for sub in ("images", "labels"):
        src = ws.final_dir / sub
        dst = out / "final_dataset" / sub
        dst.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            for p in src.iterdir():
                if p.is_file() and not (dst / p.name).exists():
                    shutil.copy2(p, dst / p.name)
    project_dir = Path(project_dir)
    for rel in ("manifests/dataset_manifest.csv", "docs/class_guide.md", "docs/bbox_guide.md",
                "docs/subject08_handoff.md"):
        if (project_dir / rel).is_file():
            shutil.copy2(project_dir / rel, out / Path(rel).name)
    return out


# ==================================================
# 5. 한 번에 만들기
# ==================================================

def export_all(project_dir, ws, manifest, history_rows, result, classes, reasons, golden=None, pilot=None):
    """산출물 전체 생성. 돌려주는 값: 만든 파일 경로 목록"""
    project_dir = Path(project_dir)
    runs = read_runs(ws.runs_path)
    n = qa_numbers(ws, manifest, history_rows, result, runs)
    written = [export_manifest(ws, project_dir)]

    report_csv = project_dir / "reports" / "validation_report.csv"
    write_report_csv(result, report_csv)
    written.append(report_csv)

    qa = project_dir / "reports" / "qa_summary.md"
    write_marked(qa, qa_summary_blocks(ws, n, reasons), QA_TEMPLATE)
    written.append(qa)

    test = project_dir / "reports" / "test_report.md"
    blocks = {"ACCEPTANCE": acceptance_block(n, golden, pilot)}
    if golden:
        blocks["GOLDEN"] = _test_block("1. Golden Test", "900장 전체 작업을 시작하기 전에 핵심 기능이 정상적으로 "
                                       "동작하는지 소수의 실제 데이터로 먼저 확인합니다.", golden)
    if pilot:
        blocks["PILOT"] = _test_block("2. Pilot Test", "실제 900장 작업을 시작하기 전에 더 많은 데이터에서 "
                                      "프로그램이 안정적으로 동작하는지 확인합니다.", pilot)
    if not test.is_file():          # 처음 만들 때는 아직 안 돌린 테스트 자리도 채워 둠
        blocks.setdefault("GOLDEN", _test_block("1. Golden Test", "", None))
        blocks.setdefault("PILOT", _test_block("2. Pilot Test", "", None))
    write_marked(test, blocks, TEST_TEMPLATE)
    written.append(test)

    handoff = project_dir / "docs" / "subject08_handoff.md"
    write_marked(handoff, {"HANDOFF": handoff_block(ws, n, classes)}, HANDOFF_TEMPLATE)
    written.append(handoff)
    return written, n
