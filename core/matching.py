"""
マッチングロジック（スコア計算 + グリーディー割り当て）
"""
from typing import Dict, List, Any
from collections import defaultdict
import pandas as pd

from core.storage import get_student_name_map, get_group_name_map


def compute_preference_scores(
    students: List[Dict],
    groups: List[Dict],
    votes: Dict,
    student_weight: float,
    group_weight: float,
    group_vote_n: int
) -> tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
    """学生側希望スコア + グループ側希望スコアを計算"""
    student_votes = votes.get("student_votes", {})
    group_votes = votes.get("group_votes", {})

    # 学生側スコア: 1位=5, 2位=4, ..., 5位=1
    student_pref: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for sid, ranks in student_votes.items():
        for gid, rank in ranks.items():
            student_pref[sid][gid] = 6 - rank

    # グループ側スコア
    group_pref: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for gid, desired_list in group_votes.items():
        for i, sid in enumerate(desired_list[:group_vote_n]):
            points = group_vote_n - i
            group_pref[gid][sid] = float(points)

    # 総合スコア
    total_score: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for s in students:
        sid = s["id"]
        for g in groups:
            gid = g["id"]
            s_score = student_pref[sid].get(gid, 0.0)
            g_score = group_pref[gid].get(sid, 0.0)
            total_score[sid][gid] = s_score * student_weight + g_score * group_weight

    return dict(student_pref), dict(group_pref), dict(total_score)


def run_greedy_matching(
    students: List[Dict],
    groups: List[Dict],
    votes: Dict,
    student_weight: float,
    group_weight: float,
    group_vote_n: int,
    min_size: int = 2,
    max_size: int = 4
) -> Dict[str, Any]:
    """
    簡易スコア合計 + グリーディー割り当て
    """
    student_map = get_student_name_map(students)
    group_map = get_group_name_map(groups)

    _, group_pref, total_score = compute_preference_scores(
        students, groups, votes, student_weight, group_weight, group_vote_n
    )

    group_capacity = {g["id"]: max_size for g in groups}
    current_assignment: Dict[str, str] = {}
    group_members: Dict[str, List[str]] = {g["id"]: [] for g in groups}
    unassigned = [s["id"] for s in students]

    # グリーディー割り当て
    while unassigned:
        best_score = -1.0
        best_pair = None

        for sid in unassigned:
            for g in groups:
                gid = g["id"]
                if group_capacity[gid] <= 0:
                    continue
                score = total_score[sid].get(gid, 0.0)
                if score > best_score:
                    best_score = score
                    best_pair = (sid, gid)

        if best_pair is None:
            break

        sid, gid = best_pair
        current_assignment[sid] = gid
        group_members[gid].append(sid)
        group_capacity[gid] -= 1
        unassigned.remove(sid)

    # 最小人数保証のための再バランス
    def _rebalance_for_min_size():
        for _ in range(10):
            small = [gid for gid, m in group_members.items() if len(m) < min_size]
            if not small:
                return True
            large = [gid for gid, m in group_members.items() if len(m) > min_size]
            if not large:
                return False

            improved = False
            for sgid in small:
                for lgid in large:
                    if len(group_members[lgid]) <= min_size:
                        continue
                    best_sid, min_loss = None, float("inf")
                    for sid in list(group_members[lgid]):
                        loss = total_score[sid].get(lgid, 0.0) - total_score[sid].get(sgid, 0.0)
                        if loss < min_loss:
                            min_loss = loss
                            best_sid = sid
                    if best_sid is not None:
                        group_members[lgid].remove(best_sid)
                        group_members[sgid].append(best_sid)
                        current_assignment[best_sid] = sgid
                        group_capacity[lgid] += 1
                        group_capacity[sgid] -= 1
                        improved = True
                        break
                if improved:
                    break
            if not improved:
                break
        return all(len(m) >= min_size for m in group_members.values())

    _rebalance_for_min_size()

    # 結果整形
    assignment_list = []
    for s in students:
        sid = s["id"]
        gid = current_assignment.get(sid)
        gname = group_map.get(gid, "未割当")
        assignment_list.append({
            "学生ID": sid,
            "学生名": student_map[sid],
            "配属グループID": gid or "",
            "配属グループ": gname,
            "総合スコア": round(total_score[sid].get(gid, 0.0), 2) if gid else 0.0
        })

    result_df = pd.DataFrame(assignment_list)

    group_summary = []
    for g in groups:
        members = [student_map[sid] for sid in group_members[g["id"]]]
        group_summary.append({
            "グループ": g["name"],
            "人数": len(members),
            "メンバー": "、".join(members) if members else "（なし）"
        })

    return {
        "assignment_df": result_df,
        "group_summary": pd.DataFrame(group_summary),
        "group_members": group_members,
        "total_score": total_score,
        "student_pref": compute_preference_scores(students, groups, votes, student_weight, group_weight, group_vote_n)[0],
        "group_pref": compute_preference_scores(students, groups, votes, student_weight, group_weight, group_vote_n)[1],
    }
