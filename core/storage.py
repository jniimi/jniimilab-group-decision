"""
データ永続化・読み書き関連の関数
"""
from pathlib import Path
from typing import Dict, List, Any
import json

DATA_DIR = Path("data")
CONFIG_PATH = DATA_DIR / "config.json"
GROUPS_PATH = DATA_DIR / "groups.json"
STUDENTS_PATH = DATA_DIR / "students.json"
VOTES_PATH = DATA_DIR / "votes.json"


def load_json(path: Path, default: Any = None) -> Any:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default if default is not None else {}


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_config() -> Dict:
    cfg = load_json(CONFIG_PATH, {
        "user_key": "jniimi2026",
        "admin_key": "admin-jniimi2026",
        "group_vote_n": 3,
        "student_weight": 0.6,
        "group_weight": 0.4,
        "max_group_size": 4,
        "min_group_size": 2
    })

    # 旧形式マイグレーション
    if "access_key" in cfg and "user_key" not in cfg:
        cfg["user_key"] = cfg["access_key"]
        if "admin_key" not in cfg:
            cfg["admin_key"] = "admin-" + cfg["access_key"]
        save_json(CONFIG_PATH, cfg)

    cfg.setdefault("max_group_size", 4)
    cfg.setdefault("min_group_size", 2)
    return cfg


def save_config(cfg: Dict) -> None:
    save_json(CONFIG_PATH, cfg)


def load_groups() -> List[Dict]:
    return load_json(GROUPS_PATH, [])


def save_groups(groups: List[Dict]) -> None:
    save_json(GROUPS_PATH, groups)


def load_students() -> List[Dict]:
    return load_json(STUDENTS_PATH, [])


def save_students(students: List[Dict]) -> None:
    save_json(STUDENTS_PATH, students)


def load_votes() -> Dict:
    return load_json(VOTES_PATH, {"student_votes": {}, "group_votes": {}})


def save_votes(votes: Dict) -> None:
    save_json(VOTES_PATH, votes)


# --- ユーティリティ ---
def get_group_name_map(groups: List[Dict]) -> Dict[str, str]:
    return {g["id"]: g["name"] for g in groups}


def get_student_name_map(students: List[Dict]) -> Dict[str, str]:
    return {s["id"]: s["name"] for s in students}


def get_group_id_map(groups: List[Dict]) -> Dict[str, str]:
    return {g["name"]: g["id"] for g in groups}


def get_student_id_map(students: List[Dict]) -> Dict[str, str]:
    return {s["name"]: s["id"] for s in students}
