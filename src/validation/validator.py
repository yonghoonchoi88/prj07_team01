"""
validator.py - 파일 · Class · 좌표 검사
=======================================

[담당]
    1) validate_config()  : configs/classes.yaml 이 올바른지 (프로그램 시작 시)
    2) LabelValidator     : WORK → FINAL 로 넘기기 전에 라벨 TXT 를 검사

[결과]
    errors   : 하나라도 있으면 FINAL 로 넘어가지 않습니다. (반드시 고쳐야 함)
    warnings : 넘어갈 수는 있지만 한 번 더 확인해 보라는 신호
"""

from pathlib import Path

COORD_EPS = 1e-4          # 소수점 6자리 저장 때문에 생기는 아주 작은 오차는 봐줍니다.
TINY_BOX_PX = 2           # 이보다 작은(픽셀) BBox 는 실수로 찍힌 점일 가능성 → 경고


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
    return errors


# ==================================================
# 2. 라벨 TXT 검사 (FINAL 로 넘기기 전)
# ==================================================

class LabelValidator:
    """
    classes: main.py 에서 만든 Class 목록
             [{"id": 0, "name": "나뭇잎·종이류", "enabled": True, "color": "#..."}, ...]
    """

    def __init__(self, classes):
        self.classes = classes

    def check(self, image_path, label_path, img_w, img_h):
        """돌려주는 값: (errors, warnings) - 둘 다 문자열 목록"""
        errors, warnings = [], []

        # ---------- ① 파일 검사 ----------
        if not Path(image_path).is_file():
            errors.append(f"이미지 파일이 없습니다: {Path(image_path).name}")
        label_path = Path(label_path)
        if not label_path.is_file():
            errors.append(f"라벨 TXT 가 없습니다: {label_path.name}")
            return errors, warnings

        with open(label_path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()

        seen = set()
        box_count = 0
        for no, line in enumerate(lines, start=1):
            parts = line.split()
            if not parts:
                continue
            if len(parts) != 5:
                errors.append(f"{no}줄: 값이 5개가 아닙니다. ({len(parts)}개)")
                continue
            try:
                cls = int(parts[0])
                xc, yc, w, h = map(float, parts[1:])
            except ValueError:
                errors.append(f"{no}줄: 숫자가 아닌 값이 있습니다.")
                continue
            box_count += 1

            # ---------- ② Class 검사 ----------
            if not (0 <= cls < len(self.classes)):
                errors.append(f"{no}줄: 없는 Class 번호입니다. ({cls})")
            elif not self.classes[cls]["enabled"]:
                errors.append(f"{no}줄: 사용하지 않는 Class 입니다. "
                              f"({cls} {self.classes[cls]['name']})")

            # ---------- ③ 좌표 검사 ----------
            if not all(-COORD_EPS <= v <= 1 + COORD_EPS for v in (xc, yc, w, h)):
                errors.append(f"{no}줄: 좌표가 0 ~ 1 범위를 벗어났습니다.")
            elif w <= 0 or h <= 0:
                errors.append(f"{no}줄: 너비/높이가 0 이하입니다.")
            elif (xc - w / 2 < -COORD_EPS or xc + w / 2 > 1 + COORD_EPS
                  or yc - h / 2 < -COORD_EPS or yc + h / 2 > 1 + COORD_EPS):
                errors.append(f"{no}줄: BBox 가 이미지 밖으로 나갑니다.")
            elif w * img_w < TINY_BOX_PX or h * img_h < TINY_BOX_PX:
                warnings.append(f"{no}줄: 아주 작은 BBox 입니다. "
                                f"({w * img_w:.1f} x {h * img_h:.1f} px)")

            key = tuple(parts)
            if key in seen:
                warnings.append(f"{no}줄: 위와 똑같은 BBox 가 중복되어 있습니다.")
            seen.add(key)

        if box_count == 0:
            warnings.append("BBox 가 0개입니다. ('이물 없음'으로 완료 처리됩니다)")
        return errors, warnings
