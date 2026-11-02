"""커플 다이어리 · 실행: streamlit run app.py
두 사람이 같은 배포 주소와 커플 코드를 사용하세요.
SQLite는 같은 서버의 사용자끼리 공유됩니다. 임시 저장소를 쓰는 호스팅은
재배포/재시작 시 데이터가 사라질 수 있으므로 영구 보관용으로 쓰지 마세요.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

st.set_page_config(page_title="우리의 하루", page_icon="💌", layout="centered", initial_sidebar_state="collapsed")
DB_PATH = Path(os.environ.get("COUPLE_DIARY_DB", "couple_diary.sqlite3"))
MOODS = ["🥰 행복해", "😊 좋아", "😌 평온해", "😴 피곤해", "🥺 속상해", "😤 화가 나"]
ROLES = ["나비", "구름"]


def database():
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            couple TEXT NOT NULL,
            author TEXT NOT NULL,
            mood TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_couple ON entries(couple, id DESC)")


def get_entries(couple):
    with database() as conn:
        return conn.execute(
            "SELECT * FROM entries WHERE couple = ? ORDER BY id DESC LIMIT 100",
            (couple,),
        ).fetchall()


def save_entry(couple, author, mood, body):
    now = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    with database() as conn:
        conn.execute(
            "INSERT INTO entries(couple, author, mood, body, created_at) VALUES (?, ?, ?, ?, ?)",
            (couple, author, mood, body, now),
        )


def mark_read(entry_id, couple, reader):
    now = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    with database() as conn:
        conn.execute(
            "UPDATE entries SET read_at = ? WHERE id = ? AND couple = ? AND author != ? AND read_at IS NULL",
            (now, entry_id, couple, reader),
        )


st.markdown("""
<style>
[data-testid="stAppViewContainer"] {background: #fff8fa;}
.block-container {max-width: 720px; padding: 0.65rem 1rem 0.6rem;}
header[data-testid="stHeader"] {height: 0; background: transparent;}
#MainMenu, footer {visibility: hidden;}
[data-testid="stToolbar"] {display: none;}
[data-testid="stVerticalBlock"] {gap: .4rem;}
[data-testid="stHorizontalBlock"] {gap: .65rem;}
h1 {font-size: 1.45rem !important; padding: 0 !important; margin: 0 !important;}
p {margin-bottom: .2rem;}
[data-testid="stCaptionContainer"] {font-size: .75rem;}
[data-testid="stForm"] {padding: .65rem; border-color: #f0dce3; background: white; border-radius: 14px;}
.stButton button, .stFormSubmitButton button {min-height: 2.15rem; border-radius: 10px;}
textarea {font-size: 16px !important;}
[data-testid="stTextInput"] input {font-size: 16px !important;}
@media (max-width: 640px) {
 .block-container {padding: .45rem .75rem .5rem;}
 [data-testid="stHorizontalBlock"] {flex-wrap: nowrap !important;}
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width: 0 !important; width: auto !important; flex: 1 1 0 !important;}
 [data-testid="stVerticalBlock"] {gap: .3rem;}
 [data-testid="stForm"] {padding: .5rem;}
}
</style>
""", unsafe_allow_html=True)

try:
    initialize()
except (sqlite3.Error, OSError):
    st.error("저장 공간에 연결하지 못했어요. 서버의 저장 경로와 쓰기 권한을 확인해 주세요.")
    st.stop()

st.title("💌 우리의 하루")
st.caption("하루의 기분을 나누고, 읽었다는 마음을 남겨요.")

left, right = st.columns([3, 2])
with left:
    code = st.text_input("커플 코드", type="password", placeholder="둘만의 코드 (8자 이상)", max_chars=64, label_visibility="collapsed")
with right:
    role = st.selectbox("내 역할", ROLES, label_visibility="collapsed")

if len(code.strip()) < 8:
    st.info("둘이 같은 코드(8자 이상)를 입력하고, 서로 다른 역할을 선택하세요.")
    st.caption("코드를 아는 사람은 일기를 볼 수 있어요. 추측하기 어려운 코드를 사용하세요.")
    st.stop()

couple = hashlib.sha256(code.strip().encode("utf-8")).hexdigest()
partner = ROLES[1] if role == ROLES[0] else ROLES[0]
scope = couple[:16] + role

if st.session_state.pop("saved_notice", False):
    st.toast("일기를 보냈어요 💌")

# 글이 저장된 후에만 다음 폼을 새로 만들어 입력 내용을 초기화합니다.
version_key = "form_version_" + scope
version = st.session_state.get(version_key, 0)
with st.form("write_" + scope + str(version)):
    mood = st.selectbox("오늘의 기분", MOODS, label_visibility="collapsed")
    body = st.text_area("오늘의 일기", height=80, max_chars=1000,
                        placeholder=f"{partner}에게 오늘의 마음을 남겨요 (최대 1,000자)",
                        label_visibility="collapsed")
    submitted = st.form_submit_button("💌 일기 보내기", use_container_width=True, type="primary")

if submitted:
    if not body.strip():
        st.toast("한 줄이라도 마음을 적어 주세요.")
    else:
        try:
            save_entry(couple, role, mood, body.strip())
            st.session_state[version_key] = version + 1
            st.session_state["saved_notice"] = True
            st.rerun()
        except sqlite3.Error:
            st.error("저장하지 못했어요. 잠시 뒤 다시 시도해 주세요.")

heading, refresh = st.columns([3, 2])
with heading:
    st.markdown("**📖 함께 쓴 일기**")
with refresh:
    if st.button("↻ 새로고침", use_container_width=True):
        st.rerun()

try:
    entries = get_entries(couple)
except sqlite3.Error:
    st.error("일기를 불러오지 못했어요. 새로고침해 주세요.")
    st.stop()

if not entries:
    st.caption("아직 일기가 없어요. 첫 번째 마음을 남겨 주세요.")
else:
    lookup = {row["id"]: row for row in entries}

    def entry_label(entry_id):
        row = lookup[entry_id]
        status = "✓ 읽음" if row["read_at"] else "• 안 읽음"
        return f"{row['created_at'][5:]} · {row['author']} · {row['mood']} · {status}"

    selected_id = st.selectbox("일기 선택 (최근 100개)", list(lookup),
                               format_func=entry_label, key="entry_" + scope,
                               label_visibility="collapsed")
    entry = lookup[selected_id]
    st.text_area("선택한 일기 내용", value=entry["body"], height=105,
                 disabled=True, key=f"body_{scope}_{selected_id}", label_visibility="collapsed")
    if entry["author"] != role and not entry["read_at"]:
        checked = st.checkbox("확인했어요 💕", key=f"read_{scope}_{selected_id}")
        if checked:
            try:
                mark_read(selected_id, couple, role)
                st.rerun()
            except sqlite3.Error:
                st.error("읽음 표시를 저장하지 못했어요. 다시 시도해 주세요.")
    elif entry["read_at"]:
        st.caption(f"✅ {entry['read_at']} · 상대방이 확인했어요")
    else:
        st.caption("💭 상대방이 아직 확인하지 않았어요")

st.caption(f"나는 {role} · 상대는 {partner} | 새 소식은 ↻ 새로고침 | 코드는 둘만의 비밀")
