"""
validator.py - 파일 · Class · 좌표 검사
=======================================

[담당]
    1) validate_config()  : configs/classes.yaml 이 올바른지 (Class · members · scene_types)
    2) LabelValidator     : 검수자가 FINAL 에 저장하기 전에 라벨 내용 + scene_type 을 검사

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

    # ---------- 작업자 / 검수자 이름 ----------
    members = data.get("members")
    if not isinstance(members, list) or not members:
        errors.append("'members:' 에 작업자 이름을 1명 이상 적어 주세요.")
    else:
        names = [str(m).strip() for m in members]
        if not all(names):
            errors.append("members 에 빈 이름이 있습니다.")
        if len(set(names)) != len(names):
            errors.append("members 에 같은 이름이 두 번 있습니다.")

    # ---------- scene_type ----------
    scenes = data.get("scene_types")
    if not isinstance(scenes, dict) or not scenes:
        errors.append("'scene_types:' 항목이 없습니다.")
    elif not all(isinstance(k, str) and k.strip() for k in scenes):
        errors.append("scene_types 의 이름(key)은 영문 글자로 적어 주세요.")
    return errors


# ==================================================
# 2. 라벨 TXT 검사 (FINAL 로 넘기기 전)
# ==================================================

class LabelValidator:
    """
    classes: main.py 에서 만든 Class 목록
             [{"id": 0, "name": "나뭇잎·종이류", "enabled": True, "color": "#..."}, ...]
    """

    def __init__(self, classes, scene_types=None):
        self.classes = classes
        self.scene_types = scene_types or {}

    def check(self, image_path, label_path, img_w, img_h):
        """디스크의 TXT 파일 검사. 돌려주는 값: (errors, warnings) - 둘 다 문자열 목록"""
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
        e, w = self.check_lines(lines, img_w, img_h)
        return errors + e, warnings + w

    def check_lines(self, lines, img_w, img_h):
        """
        TXT 내용(줄 목록) 검사. 저장하기 '전'에 미리 검사할 수 있도록 파일과 분리했습니다.
        돌려주는 값: (errors, warnings)
        """
        errors, warnings = [], []
        seen = set()
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
        return errors, warnings

    def check_scene(self, scene_type, box_count):
        """
        scene_type 과 BBox 개수가 서로 말이 되는지 검사합니다.
        (scene_type 은 YOLO Class 가 아니라 '이미지 전체'에 대한 정보)
        """
        errors, warnings = [], []
        if not scene_type:
            errors.append("scene_type 을 선택하지 않았습니다.")
            return errors, warnings
        if self.scene_types and scene_type not in self.scene_types:
            errors.append(f"알 수 없는 scene_type 입니다: {scene_type}")
            return errors, warnings

        if scene_type == "normal_kimchi" and box_count > 0:
            warnings.append(f"scene_type 이 '김치만(normal_kimchi)'인데 BBox 가 {box_count}개 있습니다.")
        if scene_type in ("kimchi_with_target", "target_only") and box_count == 0:
            warnings.append(f"scene_type 이 '{self.scene_types.get(scene_type, scene_type)}'인데 "
                            "BBox 가 0개입니다.")
        if scene_type == "other_review":
            warnings.append("'바로 분류하기 어려운 이미지(other_review)' 입니다. 이대로 FINAL 로 확정할까요?")
        return errors, warnings
