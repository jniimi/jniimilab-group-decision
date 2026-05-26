"""
ゼミ 2・3年生 研究グループ マッチングシステム
メインエントリポイント（UI層）

フロントエンドを大きく変更したい場合は、このファイルを主に編集してください。
ビジネスロジックは core/ 以下に分離されています。
"""

import streamlit as st
import pandas as pd
from typing import Dict, List

from core.storage import (
    load_config, save_config,
    load_groups, save_groups,
    load_students, save_students,
    load_votes, save_votes,
    get_group_name_map, get_student_name_map,
    get_group_id_map, get_student_id_map,
)
from core.matching import run_greedy_matching


# ==================== UI コンポーネント ====================
def render_student_voting(students: List[Dict], groups: List[Dict], votes: Dict):
    st.subheader("2年生として投票する")
    st.caption(f"{len(groups)}つの研究グループを希望順に1位〜{len(groups)}位まで順位付けてください。")

    student_map = get_student_name_map(students)
    group_map = get_group_name_map(groups)
    group_names = [g["name"] for g in groups]

    selected_name = st.selectbox(
        "あなたの名前を選んでください",
        options=list(student_map.values()),
        index=0,
        key="student_select"
    )
    sid = get_student_id_map(students).get(selected_name)

    student_votes = votes.get("student_votes", {})
    current_vote = student_votes.get(sid, {})

    total_voted = len(student_votes)
    st.caption(f"現在の投票進捗：2年生 {total_voted} / {len(students)} 名が投票済み")

    if current_vote:
        st.info(f"あなたはすでに投票済みです。変更したい場合は下のフォームから再送信してください。")
        current_ranks = {gid: rank for gid, rank in current_vote.items()}
        current_display = []
        for gid, rank in sorted(current_ranks.items(), key=lambda x: x[1]):
            current_display.append(f"{rank}位: {group_map.get(gid, gid)}")
        st.write("現在の投票内容: " + "  /  ".join(current_display))

    num_groups = len(groups)

    with st.form("student_vote_form", clear_on_submit=False):
        st.write(f"**希望順位を入力してください（{num_groups}グループすべてに順位を付けてください）**")

        rank_to_group: Dict[int, str] = {}
        cols = st.columns(num_groups)
        rank_labels = [f"{i}位" + ("（最も行きたい）" if i == 1 else "") for i in range(1, num_groups + 1)]
        default_indices = list(range(0, num_groups * 2, 2))

        for i, (col, label) in enumerate(zip(cols, rank_labels)):
            rank = i + 1
            with col:
                choice = st.selectbox(
                    label,
                    options=group_names,
                    key=f"rank_{rank}",
                    index=default_indices[i] % num_groups
                )
                rank_to_group[rank] = choice

        submitted = st.form_submit_button("投票を送信する", type="primary", use_container_width=True)

    if submitted:
        chosen = list(rank_to_group.values())
        if len(set(chosen)) != num_groups:
            st.error(f"同じグループを複数順位に選ぶことはできません。{num_groups}グループすべてに異なる順位を付けてください。")
            return

        gid_map = get_group_id_map(groups)
        new_ranks = {gid_map[name]: rank for rank, name in rank_to_group.items()}

        if "student_votes" not in votes:
            votes["student_votes"] = {}
        votes["student_votes"][sid] = new_ranks
        save_votes(votes)

        st.success(f"{selected_name} さんの投票を受け付けました！")
        st.balloons()
        st.rerun()


def render_group_voting(students: List[Dict], groups: List[Dict], votes: Dict, config: Dict):
    st.subheader("3年生グループとして投票する")
    st.caption(f"「欲しい」と思う2年生を上位 {config['group_vote_n']} 人まで選んでください（1番欲しい人から順に）。")

    group_map = get_group_name_map(groups)
    student_map = get_student_name_map(students)
    student_names = list(student_map.values())

    selected_group_name = st.selectbox(
        "あなたの研究グループを選んでください",
        options=list(group_map.values()),
        key="group_select"
    )
    gid = get_group_id_map(groups).get(selected_group_name)

    group_votes = votes.get("group_votes", {})
    current = group_votes.get(gid, [])

    total_group_voted = len(group_votes)
    st.caption(f"現在の投票進捗：3年生グループ {total_group_voted} / {len(groups)} グループが投票済み")

    if current:
        current_names = [student_map.get(sid, sid) for sid in current]
        st.info(f"現在の投票: {' → '.join(current_names)}")

    n = int(config.get("group_vote_n", 3))

    with st.form("group_vote_form"):
        st.write(f"**上位 {n} 人を、1番欲しい人から順に選んでください**")

        selections = []
        remaining_students = student_names.copy()

        for i in range(n):
            label = f"{i+1}番目に欲しい学生"
            default_idx = min(i, len(remaining_students)-1) if remaining_students else 0
            choice = st.selectbox(
                label,
                options=remaining_students if remaining_students else ["（候補なし）"],
                key=f"group_rank_{i}"
            )
            selections.append(choice)
            if choice in remaining_students:
                remaining_students.remove(choice)

        submitted = st.form_submit_button("グループの希望を送信する", type="primary", use_container_width=True)

    if submitted:
        sid_map = get_student_id_map(students)
        new_list = [sid_map[name] for name in selections if name in sid_map]

        if len(new_list) != n:
            st.error("人数が足りません。もう一度選択してください。")
            return

        if "group_votes" not in votes:
            votes["group_votes"] = {}
        votes["group_votes"][gid] = new_list
        save_votes(votes)

        st.success(f"{selected_group_name} の希望を受け付けました！")
        st.rerun()


def render_admin(students: List[Dict], groups: List[Dict], votes: Dict, config: Dict):
    st.subheader("管理者画面")

    # --- 設定変更 ---
    with st.expander("⚙️ マッチング設定（重み・N・定員）", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            new_n = st.slider("3年生が投票できる上限人数（N）", 1, 5, int(config.get("group_vote_n", 3)))
        with col2:
            new_student_w = st.slider("学生側の希望の重み", 0.0, 1.0, float(config.get("student_weight", 0.6)), 0.05)

        new_group_w = round(1.0 - new_student_w, 2)
        st.caption(f"現在の重み → 学生: {new_student_w:.0%} / グループ: {new_group_w:.0%}")

        st.divider()

        col3, col4 = st.columns(2)
        with col3:
            current_max = int(config.get("max_group_size", 4))
            new_max_size = st.slider(
                "1グループあたりの上限人数",
                min_value=1, max_value=10, value=current_max, step=1,
                help="これを超えて学生を割り当てません"
            )
        with col4:
            current_min = int(config.get("min_group_size", 2))
            new_min_size = st.slider(
                "1グループあたりの下限人数（目標）",
                min_value=0, max_value=5, value=current_min, step=1,
                help="マッチング後にこの人数を下回るグループをできるだけ減らすための再バランス目標値"
            )

        if new_min_size > new_max_size:
            st.warning("下限は上限以下にしてください。自動で調整します。")
            new_min_size = new_max_size

        if st.button("マッチング設定を保存", type="secondary"):
            config["group_vote_n"] = new_n
            config["student_weight"] = new_student_w
            config["group_weight"] = new_group_w
            config["max_group_size"] = new_max_size
            config["min_group_size"] = new_min_size
            save_config(config)
            st.success("マッチング設定を保存しました")
            st.rerun()

    # --- アクセスキー管理 ---
    with st.expander("🔑 アクセスキー管理", expanded=False):
        st.warning("ここでキーを変更すると、すぐに反映されます。変更後は新しいキーで再ログインが必要になります。", icon="⚠️")

        current_student_key = config.get("student_key", "")
        current_group_key = config.get("group_key", "")
        current_admin_key = config.get("admin_key", "")

        new_student_key = st.text_input("2年生専用キー", value=current_student_key, type="password")
        new_group_key = st.text_input("3年生グループ専用キー", value=current_group_key, type="password")
        new_admin_key = st.text_input("管理者用キー", value=current_admin_key, type="password")

        if st.button("アクセスキーを更新", type="primary"):
            if not new_admin_key:
                st.error("管理者用キーは必須です")
            elif new_student_key and new_student_key == new_group_key:
                st.error("2年生専用キーと3年生グループ専用キーは異なるものにしてください")
            else:
                config["student_key"] = new_student_key
                config["group_key"] = new_group_key
                config["admin_key"] = new_admin_key
                save_config(config)
                st.success("アクセスキーを更新しました。次回から新しいキーを使用してください。")
                st.rerun()

    # --- 投票状況 ---
    st.markdown("### 投票状況")
    st.caption(f"登録人数：2年生 **{len(students)}名** / 研究グループ **{len(groups)}グループ**（`data/students.json` / `data/groups.json` から自動判定）")

    student_votes = votes.get("student_votes", {})
    group_votes = votes.get("group_votes", {})

    col1, col2 = st.columns(2)
    with col1:
        st.metric("2年生の投票完了数", f"{len(student_votes)} / {len(students)}")
    with col2:
        st.metric("3年生グループの投票完了数", f"{len(group_votes)} / {len(groups)}")

    with st.expander("投票済み一覧（管理者限定）"):
        voted_students = [get_student_name_map(students).get(sid, sid) for sid in student_votes.keys()]
        st.write("2年生:", ", ".join(voted_students) if voted_students else "まだ誰も投票していません")

        voted_groups = [get_group_name_map(groups).get(gid, gid) for gid in group_votes.keys()]
        st.write("3年生グループ:", ", ".join(voted_groups) if voted_groups else "まだ投票なし")

    # --- マッチング実行 ---
    st.markdown("### マッチング実行")
    if st.button("マッチングを実行する", type="primary", use_container_width=True):
        with st.spinner("計算中..."):
            result = run_greedy_matching(
                students,
                groups,
                votes,
                config["student_weight"],
                config["group_weight"],
                config["group_vote_n"],
                min_size=config.get("min_group_size", 2),
                max_size=config.get("max_group_size", 4),
            )
            st.session_state["last_matching_result"] = result
            st.success("マッチングが完了しました！下の結果を確認してください。")

    # 結果表示
    if "last_matching_result" in st.session_state:
        result = st.session_state["last_matching_result"]
        st.markdown("#### 配属結果")

        used_min = config.get("min_group_size", 2)
        used_max = config.get("max_group_size", 4)
        st.caption(f"この結果は「上限 {used_max}名 / 下限 {used_min}名」を基準に計算されました")

        st.dataframe(result["assignment_df"], use_container_width=True, hide_index=True)
        st.markdown("#### グループ別まとめ")
        st.dataframe(result["group_summary"], use_container_width=True, hide_index=True)

        csv = result["assignment_df"].to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "配属結果をCSVでダウンロード",
            data=csv,
            file_name="matching_result.csv",
            mime="text/csv"
        )

        with st.expander("詳細スコア（上級者向け）"):
            st.caption("学生ごとの各グループに対する総合スコアです。")
            score_rows = []
            student_map = get_student_name_map(students)
            group_map = get_group_name_map(groups)
            for sid in [s["id"] for s in students]:
                row = {"学生": student_map[sid]}
                for g in groups:
                    row[g["name"]] = round(result["total_score"][sid].get(g["id"], 0), 2)
                score_rows.append(row)
            st.dataframe(pd.DataFrame(score_rows), use_container_width=True, hide_index=True)

    # --- 名前リスト編集 ---
    st.markdown("### 名前リストの編集")
    with st.expander("グループ名を編集"):
        groups_df = pd.DataFrame(groups)
        edited_groups = st.data_editor(
            groups_df, num_rows="fixed", use_container_width=True, key="edit_groups"
        )
        if st.button("グループ名を保存"):
            new_groups = edited_groups.to_dict("records")
            save_groups(new_groups)
            st.success("グループ名を更新しました")
            st.rerun()

    with st.expander("学生名を編集"):
        students_df = pd.DataFrame(students)
        edited_students = st.data_editor(
            students_df, num_rows="fixed", use_container_width=True, key="edit_students"
        )
        if st.button("学生名を保存"):
            new_students = edited_students.to_dict("records")
            save_students(new_students)
            st.success("学生名を更新しました")
            st.rerun()

    # --- データ管理 ---
    st.markdown("### データ管理")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("投票データだけリセット", type="secondary"):
            votes["student_votes"] = {}
            votes["group_votes"] = {}
            save_votes(votes)
            if "last_matching_result" in st.session_state:
                del st.session_state["last_matching_result"]
            st.warning("投票データをリセットしました")
            st.rerun()
    with col2:
        if st.button("全データを初期状態に戻す", type="secondary"):
            save_votes({"student_votes": {}, "group_votes": {}})
            if "last_matching_result" in st.session_state:
                del st.session_state["last_matching_result"]
            st.warning("投票データのみ初期化しました")
            st.rerun()


# ==================== メインアプリ ====================
def main():
    st.set_page_config(
        page_title="jniimilab Grouping System",
        page_icon="🎓",
        layout="centered"
    )

    st.title("🎓 jniimilab Grouping System")
    st.caption("配布されたアクセスキーを入力して進んでください。")

    # データ読み込み
    config = load_config()
    groups = load_groups()
    students = load_students()
    votes = load_votes()

    # ========== アクセスキー認証 ==========
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.user_role = None  # "student", "group", "general", "admin"

    if not st.session_state.authenticated:
        st.markdown("---")
        with st.container(border=True):
            st.subheader("アクセスキー入力")
            st.caption("配布されたキーを入力してください。2年生専用キー、3年生グループ専用キー、管理者用キーのいずれかをお使いください。")
            key_input = st.text_input(
                "アクセスキーを入力してください",
                type="password",
                placeholder="アクセスキー"
            )
            if st.button("入室する", type="primary"):
                student_key = config.get("student_key", "")
                group_key = config.get("group_key", "")
                admin_key = config.get("admin_key", "")

                if key_input == admin_key:
                    st.session_state.authenticated = True
                    st.session_state.user_role = "admin"
                    st.success("管理者として認証されました。管理画面を表示します。")
                    st.rerun()

                elif student_key and key_input == student_key:
                    st.session_state.authenticated = True
                    st.session_state.user_role = "student"
                    st.success("2年生として認証されました。")
                    st.rerun()

                elif group_key and key_input == group_key:
                    st.session_state.authenticated = True
                    st.session_state.user_role = "group"
                    st.success("3年生グループとして認証されました。")
                    st.rerun()

                else:
                    st.error("アクセスキーが違います")
        render_footer()
        st.stop()

    # ========== 認証後メイン ==========
    role = st.session_state.get("user_role")

    if role == "admin":
        st.success("管理者モードで入室中", icon="🔐")
        st.caption("この画面は管理者限定です。一般ユーザーには一切表示されません。")

        if st.button("ログアウト（アクセスキー画面に戻る）", type="secondary"):
            st.session_state.authenticated = False
            st.session_state.user_role = None
            st.rerun()

        st.divider()
        render_admin(students, groups, votes, config)

    elif role == "student":
        # 2年生専用キー → 自動で2年生投票画面のみ
        st.success("2年生モードで入室中", icon="🧑‍🎓")
        st.caption("2年生として投票してください。")

        if st.button("ログアウト（アクセスキー画面に戻る）", type="secondary"):
            st.session_state.authenticated = False
            st.session_state.user_role = None
            st.rerun()

        st.divider()
        render_student_voting(students, groups, votes)

    elif role == "group":
        # 3年生グループ専用キー → 自動で3年生投票画面のみ
        st.success("3年生グループモードで入室中", icon="👥")
        st.caption("あなたの研究グループとして投票してください。")

        if st.button("ログアウト（アクセスキー画面に戻る）", type="secondary"):
            st.session_state.authenticated = False
            st.session_state.user_role = None
            st.rerun()

        st.divider()
        render_group_voting(students, groups, votes, config)

    else:
        # 不明なロール（通常は発生しない）
        st.error("不明なアクセスキーです。管理者にお問い合わせください。")
        if st.button("ログアウト（アクセスキー画面に戻る）", type="secondary"):
            st.session_state.authenticated = False
            st.session_state.user_role = None
            st.rerun()

    # フッター
    render_footer()


def render_footer():
    st.divider()
    st.caption("©jniimilab | グループ意思決定支援ツール（開発版）")
    st.caption("Proudly co-built with Grok & [jniimilab](https://jniimilab.ai)")


if __name__ == "__main__":
    main()
