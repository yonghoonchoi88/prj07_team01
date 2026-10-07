"""
make_reports.py - 화면 없이 산출물만 다시 만들기 (명령어 버전)
=============================================================

프로그램의 [검사 > 산출물 생성] 과 같은 일을 터미널에서 합니다.
팀장이 merge_results.py 로 팀원 결과를 합친 뒤, 최종 숫자를 뽑을 때 쓰면 편합니다.

[사용법]  (프로젝트 폴더에서)
    python -m tools.make_reports --data ../data            # Validation + 산출물
    python -m tools.make_reports --data ../data --tests    # Golden · Pilot 자동 테스트까지

[만드는 파일]
    manifests/dataset_manifest.csv   reports/validation_report.csv
    reports/qa_summary.md            reports/test_report.md
    docs/subject08_handoff.md
    (직접 쓴 메모는 지워지지 않습니다. <!-- AUTO:... --> 영역만 새로 씁니다)
"""

import argparse
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from main import CONFIG_PATH, load_config                      # noqa: E402
from src.qa.reports import export_all                          # noqa: E402
from src.qa.self_test import run_tests                         # noqa: E402
from src.records.history import History                        # noqa: E402
from src.records.manifest import Manifest                      # noqa: E402
from src.validation.validator import LabelValidator, save_run, validate_dataset  # noqa: E402
from src.yolo.yolo_loader import build_workspace               # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="QA Summary · Test Report · Manifest 산출물 생성")
    parser.add_argument("--data", required=True, help="data 폴더 (안에 raw/ work/ final/ manifests/)")
    parser.add_argument("--tests", action="store_true", help="Golden · Pilot 자동 테스트도 실행")
    args = parser.parse_args()

    config = load_config(CONFIG_PATH)
    ws = build_workspace(args.data)
    if not ws.items:
        sys.exit(f"이미지가 없습니다: {args.data}  (data/raw/ 에 원본 데이터셋이 있는지 확인)")
    manifest = Manifest(ws.manifest_path, ws.items)
    history = History(ws.history_path)
    validator = LabelValidator(config["classes"], config["scene_types"])

    golden = pilot = None
    if args.tests:
        rules = config["rules"]
        g, p = rules.get("golden_test_size", 20), rules.get("pilot_test_size", 50)
        print(f"Golden {g}장 · Pilot {p}장 자동 테스트 중...")
        golden = run_tests(ws.items, g, config["classes"], validator)
        pilot = run_tests(ws.items, p, config["classes"], validator, offset=max(1, len(ws.items) // (2 * p)))
        print(f"  Golden {golden['image_pass']}/{golden['n']} · Pilot {pilot['image_pass']}/{pilot['n']} PASS")

    result = validate_dataset(ws, manifest, validator)
    save_run(result, ws.runs_path)
    print(f"Validation: 전체 {result.total}장 · PASS {result.pass_count} · FAIL {result.fail_count}건")

    written, n = export_all(PROJECT_DIR, ws, manifest, history.read_all(), result,
                            config["classes"], config["review_reasons"], golden, pilot)
    c = n["counts"]
    print(f"QA PASS {c['PASS']}/{n['total']} · REVIEW {c['REVIEW']} · 미작업 {c['TODO']}")
    for p in written:
        print("  ✔", p.relative_to(PROJECT_DIR))


if __name__ == "__main__":
    main()
