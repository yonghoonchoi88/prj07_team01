"""
validator.py - 파일 · Class · 좌표 검사
=======================================

[담당]
    1) validate_config()    : configs/classes.yaml 이 올바른지 (프로그램 시작 시)
    2) LabelValidator       : 한 장 저장 직전 검사 (검수자 QA PASS 전에 반드시 통과)
    3) validate_dataset()   : 900장 전체 자동 Validation  → QA Summary(8번) 의 숫자가 됩니다.

[자동 Validation 오류 종류]  (교과7 8번 QA Summary 기준)
    pair          이미지-TXT Pair 오류      (TXT 없음, FINAL 쌍 누락, 짝 없는 TXT)
    format        좌표 형식 오류            (값 5개가 아님, 숫자가 아님)
    class_id      Class ID 오류             (0~6 범위 밖)
    unused_class  사용하지 않는 Class        (4 고무장갑 → 임의 삭제 말고 REVIEW)
    bbox_bounds   BBox 이미지 경계 초과       (좌표가 0~1 밖, 너비·높이 0 이하)
    empty_txt     Empty TXT 확인 필요        (빈 TXT 인데 scene_type 이 normal_kimchi 가 아님)
    scene         scene_type 불일치          (normal_kimchi 인데 BBox 가 있음)
    manifest      Manifest 상태 오류         (REVIEW 인데 사유 없음, PASS 인데 REVIEW 등)

    ※ Empty TXT 는 무조건 오류가 아닙니다. normal_kimchi(검출 대상 없음)이면 정상 PASS.
"""

import csv
from datetime import datetime
from pathlib import Path

COORD_EPS = 1e-4          # 소수점 6자리 저장 때문에 생기는 아주 작은 오차는 봐줍니다.
TINY_BOX_PX = 2           # 이보다 작은(픽셀) BBox 는 실수로 찍힌 점일 가능성 → 경고

ERROR_TYPES = {
    "pair": "이미지-TXT Pair 오류",
    "format": "좌표 형식 오류",
    "class_id": "Class ID 오류",
    "unused_class": "사용하지 않는 Class(4)",
    "bbox_bounds": "BBox 이미지 경계 초과",
    "empty_txt": "Empty TXT 확인 필요",
    "scene": "scene_type 불일치",
    "manifest": "Manifest 상태 오류",
}
NORMAL_SCENE = "normal_kimchi"


# ==================================================
# 1. 설정 파일(classes.yaml) 검사
# ==================================================

def validate_config(data):
    """classes.yaml 을 읽은 dict 를 검사해서 에러 메시지 목록을 돌려줍니다. (빈 목록 = 통과)"""
    errors = []
    if not isinstance(data, dict) or not isinstance(data.get("classes"), dict):
        return ["'classes:' 항목이 없습니다."]

    classes = data["classes"]
    if not classes:
        return ["Class 가 하나도 없습니다."]

    ids = []
    for key, info in classes.items():
        if not isinstance(key, int) or isinstance(key, bool):
            errors.append(f"Class 번호는 정수여야 합니다: {key!r}")
            continue
        ids.append(key)
        if not isinstance(info, dict):
            errors.append(f"Class {key}: name / enabled 를 적어 주세요.")
            continue
        if not str(info.get("name", "")).strip():
            errors.append(f"Class {key}: name 이 비어 있습니다.")
        if "enabled" in info and not isinstance(info["enabled"], bool):
            errors.append(f"Class {key}: enabled 는 true / false 로 적어 주세요.")

    # YOLO class_id 는 0, 1, 2 ... 빈칸 없이 이어져야 합니다.
    if ids and sorted(ids) != list(range(len(ids))):
        errors.append(f"Class 번호는 0부터 빈칸 없이 이어져야 합니다. 현재: {sorted(ids)}")
    if not errors and not any(info.get("enabled", True) for info in classes.values()):
        errors.append("enabled: true 인 Class 가 하나도 없습니다.")

    members = data.get("members")
    if not isinstance(members, list) or not members:
        errors.append("'members:' 에 작업자 이름을 1명 이상 적어 주세요.")
    else:
        names = [str(m).strip() for m in members]
        if not all(names):
            errors.append("members 에 빈 이름이 있습니다.")
        if len(set(names)) != len(names):
            errors.append("members 에 같은 이름이 두 번 있습니다.")

    for key in ("scene_types", "review_reasons"):
        block = data.get(key)
        if not isinstance(block, dict) or not block:
            errors.append(f"'{key}:' 항목이 없습니다.")
        elif not all(isinstance(k, str) and k.strip() for k in block):
            errors.append(f"{key} 의 이름(key)은 영문 글자로 적어 주세요.")
    return errors


# ==================================================
# 2. TXT 내용 검사 (한 장)
# ==================================================

class LabelValidator:
    """
    classes      : [{"id": 0, "name": "...", "enabled": True, ...}, ...]
    scene_types  : {"kimchi_with_target": "...", ...}
    """

    def __init__(self, classes, scene_types=None):
        self.classes = classes
        self.scene_types = scene_types or {}

    def parse_lines(self, lines):
        """
        TXT 줄 목록 → (BBox 개수, 오류 [(종류, 메시지)], 경고 [메시지])
        저장 전(메모리의 BBox)과 저장 후(디스크의 TXT) 모두 이 함수 하나로 검사합니다.
        """
        errors, warnings, seen, count = [], [], set(), 0
        for no, line in enumerate(lines, start=1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) != 5:
                errors.append(("format", f"{no}줄: 값이 5개가 아닙니다. ({len(parts)}개)"))
                continue
            try:
                cls = int(parts[0])
                xc, yc, w, h = map(float, parts[1:])
            except ValueError:
                errors.append(("format", f"{no}줄: 숫자가 아닌 값이 있습니다."))
                continue
            count += 1

            if not (0 <= cls < len(self.classes)):
                errors.append(("class_id", f"{no}줄: 없는 Class 번호입니다. ({cls})"))
            elif not self.classes[cls]["enabled"]:
                errors.append(("unused_class", f"{no}줄: 사용하지 않는 Class 입니다. "
                                               f"({cls} {self.classes[cls]['name']})"))

            if not all(-COORD_EPS <= v <= 1 + COORD_EPS for v in (xc, yc, w, h)):
                errors.append(("bbox_bounds", f"{no}줄: 좌표가 0 ~ 1 범위를 벗어났습니다."))
            elif w <= 0 or h <= 0:
                errors.append(("bbox_bounds", f"{no}줄: 너비/높이가 0 이하입니다."))
            elif (xc - w / 2 < -COORD_EPS or xc + w / 2 > 1 + COORD_EPS
                  or yc - h / 2 < -COORD_EPS or yc + h / 2 > 1 + COORD_EPS):
                errors.append(("bbox_bounds", f"{no}줄: BBox 가 이미지 밖으로 나갑니다."))

            key = tuple(parts)
            if key in seen:
                warnings.append(f"{no}줄: 위와 똑같은 BBox 가 중복되어 있습니다.")
            seen.add(key)
        return count, errors, warnings

    def check_scene(self, scene_type, box_count):
        """scene_type 과 BBox 개수가 서로 말이 되는지. 돌려주는 값: (오류 [(종류, 메시지)], 경고)"""
        errors, warnings = [], []
        if not scene_type:
            errors.append(("manifest", "scene_type 을 선택하지 않았습니다."))
            return errors, warnings
        if self.scene_types and scene_type not in self.scene_types:
            errors.append(("manifest", f"알 수 없는 scene_type 입니다: {scene_type}"))
            return errors, warnings
        if scene_type == NORMAL_SCENE and box_count > 0:
            errors.append(("scene", f"scene_type 이 normal_kimchi(검출 대상 없음)인데 BBox 가 {box_count}개 있습니다."))
        if scene_type != NORMAL_SCENE and box_count == 0:
            errors.append(("empty_txt", f"BBox 가 0개입니다. 검출 대상이 없으면 scene_type 을 normal_kimchi 로, "
                                        f"있으면 BBox 를 추가하세요. (지금: {scene_type})"))
        if scene_type == "other_review":
            warnings.append("scene_type 이 other_review(바로 분류하기 어려운 이미지)입니다.")
        return errors, warnings

    def check_before_pass(self, lines, scene_type, img_w=None, img_h=None):
        """검수자 QA PASS 직전 검사. 돌려주는 값: (오류 메시지 목록, 경고 메시지 목록)"""
        count, errors, warnings = self.parse_lines(lines)
        e2, w2 = self.check_scene(scene_type, count)
        if img_w and img_h:
            for no, line in enumerate(lines, start=1):
                p = line.split()
                if len(p) == 5:
                    try:
                        w, h = float(p[3]) * img_w, float(p[4]) * img_h
                    except ValueError:
                        continue
                    if w < TINY_BOX_PX or h < TINY_BOX_PX:
                        warnings.append(f"{no}줄: 아주 작은 BBox 입니다. ({w:.1f} x {h:.1f} px)")
        return [m for _, m in errors + e2], warnings + w2


# ==================================================
# 3. 900장 전체 자동 Validation
# ==================================================

class ValidationResult:
    def __init__(self):
        self.run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.images = []          # [{"index", "file_name", "stage", "errors": [(종류, 메시지)]}]
        self.orphans = []         # [{"file_name", "errors"}]  이미지 없이 남은 TXT 등

    @property
    def failed(self):
        return [r for r in self.images if r["errors"]] + self.orphans

    @property
    def total(self):
        return len(self.images)

    @property
    def pass_count(self):
        return sum(1 for r in self.images if not r["errors"])

    @property
    def fail_count(self):
        return len(self.failed)

    def by_type(self):
        """오류 종류별 건수 (한 이미지에 같은 종류가 여러 줄이어도 1건)"""
        counts = {k: 0 for k in ERROR_TYPES}
        for r in self.failed:
            for code in {c for c, _ in r["errors"]}:
                counts[code] += 1
        return counts


def _read_lines(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return f.read().splitlines()


def validate_dataset(ws, manifest, validator):
    """
    작업 공간 전체 검사. 이미지마다 '지금 쓰이는 라벨'을 검사합니다.
        QA PASS → final (TXT + 이미지 한 쌍 확인)   /   1차 검수 → work   /   미작업 → raw
    """
    from src.records.manifest import QA_PASS, STATUS_REVIEW, STATUSES
    from src.yolo.yolo_loader import STAGE_FINAL, STAGE_RAW, STAGE_WORK

    result = ValidationResult()
    keys = set()
    for i, it in enumerate(ws.items):
        keys.add(Path(it.key).stem)
        row = manifest.get(it.key)
        errors = []
        if row["qa_status"] == QA_PASS:
            stage, label = STAGE_FINAL, it.label_path(STAGE_FINAL)
            if not it.final_image_path.is_file():
                errors.append(("pair", "QA PASS 인데 final/images 에 이미지가 없습니다."))
        elif it.label_path(STAGE_WORK).is_file():
            stage, label = STAGE_WORK, it.label_path(STAGE_WORK)
        else:
            stage, label = STAGE_RAW, it.label_path(STAGE_RAW)

        if not label.is_file():
            errors.append(("pair", f"라벨 TXT 가 없습니다. ({stage})"))
        else:
            count, line_errors, _ = validator.parse_lines(_read_lines(label))
            errors += line_errors
            scene = row["scene_type"]
            if count == 0 and scene != NORMAL_SCENE:
                errors.append(("empty_txt", "BBox 가 0개입니다. 이미지 확인 필요 "
                                            "(검출 대상이 없으면 scene_type = normal_kimchi)"))
            if scene == NORMAL_SCENE and count > 0:
                errors.append(("scene", f"normal_kimchi 인데 BBox 가 {count}개 있습니다."))

        status, reason = row["status"], row["review_reason"]
        if status and status not in STATUSES:
            errors.append(("manifest", f"알 수 없는 status: {status}"))
        if status == STATUS_REVIEW and not reason:
            errors.append(("manifest", "REVIEW 인데 review_reason 이 비어 있습니다."))
        if reason and status != STATUS_REVIEW:
            errors.append(("manifest", "REVIEW 가 아닌데 review_reason 이 적혀 있습니다."))
        if row["qa_status"] == QA_PASS and status == STATUS_REVIEW:
            errors.append(("manifest", "REVIEW 상태인데 QA PASS 입니다. (미해결 REVIEW 는 FINAL 불가)"))
        if row["qa_status"] == QA_PASS and not row["scene_type"]:
            errors.append(("manifest", "QA PASS 인데 scene_type 이 비어 있습니다."))

        result.images.append({"index": i, "file_name": it.key, "stage": stage, "errors": errors})

    # 짝 없는 파일: final/work 에 TXT 는 있는데 이미지가 목록에 없음 / final 이미지만 있음
    for folder, what in ((ws.final_dir / "labels", "final TXT"), (ws.final_dir / "images", "final 이미지"),
                         (ws.work_dir / "labels", "work TXT")):
        if folder.is_dir():
            for p in sorted(folder.iterdir()):
                if p.is_file() and p.stem not in keys:
                    result.orphans.append({"file_name": f"{folder.parent.name}/{folder.name}/{p.name}",
                                           "stage": "-", "index": None,
                                           "errors": [("pair", f"짝이 되는 원본 이미지가 없는 {what}")]})
    for key in manifest.orphans:
        result.orphans.append({"file_name": key, "stage": "-", "index": None,
                               "errors": [("manifest", "manifest 에는 있는데 원본 이미지가 없습니다.")]})
    return result


# ==================================================
# 4. 결과 저장 (Validation 실행 기록 / 상세 CSV)
# ==================================================

RUN_COLUMNS = ["run_at", "total", "pass", "fail"] + list(ERROR_TYPES) + ["failed_files"]


def save_run(result, runs_path):
    """Validation 한 번 실행할 때마다 한 줄씩 기록 → QA Summary 의 '최초 결과 → 최종 결과' 비교에 사용"""
    runs_path = Path(runs_path)
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    new = not runs_path.is_file() or runs_path.stat().st_size == 0
    row = {"run_at": result.run_at, "total": result.total, "pass": result.pass_count,
           "fail": result.fail_count, **result.by_type(),
           "failed_files": ";".join(r["file_name"] for r in result.failed)}
    with open(runs_path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RUN_COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)


def read_runs(runs_path):
    runs_path = Path(runs_path)
    if not runs_path.is_file():
        return []
    with open(runs_path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_report_csv(result, path):
    """이미지별 상세 결과 (reports/validation_report.csv)"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file_name", "checked_label", "result", "error_types", "messages"])
        for r in result.images + result.orphans:
            codes = sorted({c for c, _ in r["errors"]})
            w.writerow([r["file_name"], r["stage"], "FAIL" if r["errors"] else "PASS",
                        ";".join(codes), " / ".join(m for _, m in r["errors"])])
