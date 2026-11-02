"""우리의 하루 — 오프라인 커플 다이어리
실행: python app.py (Python 3.10 이상, tkinter 필요)
외부 패키지/인터넷/웹 서버 불필요. 같은 컴퓨터에서 역할을 바꿔 사용합니다.
일기는 이 파일 옆 couple_diary_offline.sqlite3에 저장됩니다.
DB 파일에 쓰기 권한이 있는 폴더에서 실행하세요. 별도의 로그인/암호화는 없습니다.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

DB_PATH = Path(__file__).resolve().with_name("couple_diary_offline.sqlite3")
ROLES = ("나비", "구름")
MOODS = ("행복해", "좋아", "평온해", "피곤해", "속상해", "화가 나")
BG = "#fff7fa"
FG = "#44343c"
ACCENT = "#bc4975"


@contextmanager
def database():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize():
    with database() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS offline_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            mood TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL,
            read_at TEXT
        )""")


def get_entries():
    with database() as conn:
        return conn.execute("SELECT * FROM offline_entries ORDER BY id DESC").fetchall()


def save_entry(author, mood, body):
    if author not in ROLES or mood not in MOODS:
        raise ValueError("올바른 역할과 기분을 선택하세요.")
    body = body.strip()
    if not body or len(body) > 1000:
        raise ValueError("일기를 1~1,000자로 작성하세요.")
    with database() as conn:
        conn.execute(
            "INSERT INTO offline_entries(author, mood, body, created_at) VALUES (?, ?, ?, ?)",
            (author, mood, body, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )


def mark_read(entry_id, reader):
    if reader not in ROLES:
        raise ValueError("올바른 역할을 선택하세요.")
    with database() as conn:
        conn.execute(
            "UPDATE offline_entries SET read_at = ? WHERE id = ? AND author != ? AND read_at IS NULL",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), entry_id, reader),
        )


class DiaryApp:
    def __init__(self, root):
        self.root = root
        root.title("우리의 하루 · 오프라인")
        root.geometry("410x630")
        root.minsize(360, 570)
        root.configure(bg=BG)
        self.entries = []
        self.role = tk.StringVar(value=ROLES[0])
        self.mood = tk.StringVar(value=MOODS[0])
        self.read_var = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="인터넷 없이, 이 컴퓨터에 자동 저장돼요.")
        self.read_status = tk.StringVar(value="첫 번째 일기를 남겨 주세요.")
        self.counter = tk.StringVar(value="0 / 1,000자")
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG, font=("맑은 고딕", 10))
        style.configure("Title.TLabel", font=("맑은 고딕", 20, "bold"), foreground=ACCENT)
        style.configure("Note.TLabel", foreground="#806776", font=("맑은 고딕", 9))
        style.configure("TButton", font=("맑은 고딕", 10), padding=5)
        style.configure("Accent.TButton", background=ACCENT, foreground="white")
        style.map("Accent.TButton", background=[("active", "#a83c66")])
        style.configure("TCombobox", fieldbackground="white", background="#f5e5ed", foreground=FG, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", "white")],
                  foreground=[("readonly", FG)], selectbackground=[("readonly", "white")],
                  selectforeground=[("readonly", FG)])
        style.configure("TCheckbutton", background=BG, foreground=FG, font=("맑은 고딕", 10))
        root.option_add("*TCombobox*Listbox.background", "white")
        root.option_add("*TCombobox*Listbox.foreground", FG)

        panel = ttk.Frame(root, padding=14)
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(6, weight=1)
        panel.rowconfigure(11, weight=1)
        ttk.Label(panel, text="우리의 하루", style="Title.TLabel").grid(row=0, sticky="w")
        ttk.Label(panel, text="마음을 남기고, 읽었다는 마음도 전해요.", style="Note.TLabel").grid(row=1, sticky="w", pady=(0, 8))

        identity = ttk.Frame(panel)
        identity.grid(row=2, sticky="ew")
        identity.columnconfigure(1, weight=1)
        ttk.Label(identity, text="지금 쓰는 사람").grid(row=0, column=0, padx=(0, 10))
        self.role_box = ttk.Combobox(identity, textvariable=self.role, values=ROLES, state="readonly", width=12)
        self.role_box.grid(row=0, column=1, sticky="ew")
        self.role_box.bind("<<ComboboxSelected>>", self.change_role)
        self.last_role = self.role.get()
        ttk.Separator(panel).grid(row=3, sticky="ew", pady=9)
        ttk.Label(panel, text="오늘의 기분").grid(row=4, sticky="w")
        ttk.Combobox(panel, textvariable=self.mood, values=MOODS, state="readonly").grid(row=5, sticky="ew", pady=(3, 5))

        self.editor = self.text_box(panel, 6, 4)
        self.editor.bind("<<Modified>>", self.update_count)
        actions = ttk.Frame(panel)
        actions.grid(row=7, sticky="ew", pady=5)
        actions.columnconfigure(0, weight=1)
        ttk.Label(actions, textvariable=self.counter, style="Note.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(actions, text="일기 남기기", style="Accent.TButton", command=self.save).grid(row=0, column=1)
        ttk.Label(panel, textvariable=self.status, style="Note.TLabel", wraplength=330).grid(row=8, sticky="w", pady=(0, 8))

        shared = ttk.Frame(panel)
        shared.grid(row=9, sticky="ew")
        shared.columnconfigure(0, weight=1)
        ttk.Label(shared, text="함께 쓴 일기").grid(row=0, column=0, sticky="w")
        ttk.Button(shared, text="새로고침", command=self.refresh).grid(row=0, column=1)
        self.entry_box = ttk.Combobox(panel, state="readonly", font=("맑은 고딕", 9))
        self.entry_box.grid(row=10, sticky="ew", pady=5)
        self.entry_box.bind("<<ComboboxSelected>>", self.display_entry)
        self.viewer = self.text_box(panel, 11, 4)
        self.viewer.configure(state="disabled")
        self.read_check = ttk.Checkbutton(panel, text="확인했어요", variable=self.read_var, command=self.acknowledge)
        self.read_check.grid(row=12, sticky="w", pady=(6, 2))
        ttk.Label(panel, textvariable=self.read_status, style="Note.TLabel", wraplength=330).grid(row=13, sticky="w")
        ttk.Label(panel, text="오프라인 · 같은 컴퓨터에서 역할을 바꿔 사용", style="Note.TLabel").grid(row=14, sticky="w", pady=(8, 0))
        self.refresh()

    def text_box(self, parent, row, height):
        frame = ttk.Frame(parent)
        frame.grid(row=row, sticky="nsew")
        widget = tk.Text(frame, height=height, width=24, wrap="word", font=("맑은 고딕", 11),
                         bg="white", fg=FG, insertbackground=FG, relief="solid", borderwidth=1,
                         padx=8, pady=6, undo=True, highlightthickness=0)
        scroll = ttk.Scrollbar(frame, command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        widget.pack(side="left", fill="both", expand=True)
        return widget

    def update_count(self, _event=None):
        if self.editor.edit_modified():
            self.counter.set(f"{len(self.editor.get('1.0', 'end-1c'))} / 1,000자")
            self.editor.edit_modified(False)

    def change_role(self, _event=None):
        # 이전 사람의 미작성 내용이 다른 사람의 이름으로 저장되는 것을 방지합니다.
        if self.editor.get("1.0", "end-1c").strip():
            if not messagebox.askyesno("역할 바꾸기", "아직 저장하지 않은 글이 있어요. 글을 지우고 역할을 바꿀까요?", parent=self.root):
                self.role.set(self.last_role)
                return
        self.editor.delete("1.0", "end")
        self.editor.edit_reset()
        self.mood.set(MOODS[0])
        self.last_role = self.role.get()
        self.status.set(f"지금은 {self.role.get()}의 차례예요.")
        self.display_entry()

    def save(self):
        try:
            save_entry(self.role.get(), self.mood.get(), self.editor.get("1.0", "end-1c"))
        except ValueError as exc:
            messagebox.showinfo("작성 확인", str(exc), parent=self.root)
            return
        except sqlite3.Error as exc:
            self.show_error(exc)
            return
        self.editor.delete("1.0", "end")
        self.editor.edit_reset()
        self.status.set("일기를 저장했어요. 상대 역할로 바꿔 확인해 보세요.")
        self.refresh(select_newest=True)

    def refresh(self, select_newest=False):
        old = self.selected_entry()
        try:
            entries = get_entries()
        except sqlite3.Error as exc:
            self.show_error(exc)
            return
        self.entries = entries
        labels = [f"{e['created_at'][5:]} · {e['author']} · {e['mood']} · {'읽음' if e['read_at'] else '미확인'}" for e in entries]
        self.entry_box.configure(values=labels)
        if entries:
            index = 0
            if old is not None and not select_newest:
                index = next((i for i, e in enumerate(entries) if e['id'] == old['id']), 0)
            self.entry_box.current(index)
        else:
            self.entry_box.set("")
        self.display_entry()

    def selected_entry(self):
        index = self.entry_box.current()
        return self.entries[index] if 0 <= index < len(self.entries) else None

    def display_entry(self, _event=None):
        entry = self.selected_entry()
        self.viewer.configure(state="normal")
        self.viewer.delete("1.0", "end")
        self.viewer.insert("1.0", entry['body'] if entry else "아직 일기가 없어요. 위에서 첫 일기를 남겨 주세요.")
        self.viewer.configure(state="disabled")
        self.read_var.set(bool(entry and entry['read_at']))
        enabled = bool(entry and entry['author'] != self.role.get() and not entry['read_at'])
        self.read_check.configure(state="normal" if enabled else "disabled")
        if not entry:
            self.read_status.set("첫 번째 일기를 남겨 주세요.")
        elif entry['read_at']:
            reader = ROLES[1] if entry['author'] == ROLES[0] else ROLES[0]
            self.read_status.set(f"{reader} 확인 완료 · {entry['read_at']}")
        elif entry['author'] == self.role.get():
            self.read_status.set("상대가 아직 확인하지 않았어요.")
        else:
            self.read_status.set("읽었다면 ‘확인했어요’를 체크해 주세요.")

    def acknowledge(self):
        entry = self.selected_entry()
        if entry is None:
            return
        try:
            mark_read(entry['id'], self.role.get())
        except (sqlite3.Error, ValueError) as exc:
            self.show_error(exc)
        self.refresh()

    def show_error(self, exc):
        messagebox.showerror("저장소 오류", f"파일을 읽거나 저장하지 못했어요.\n쓰기 가능한 폴더인지 확인해 주세요.\n\n{exc}", parent=self.root)


def main():
    root = tk.Tk()
    root.withdraw()
    try:
        initialize()
    except (sqlite3.Error, OSError) as exc:
        messagebox.showerror("시작 실패", f"저장소를 만들지 못했어요.\napp.py를 쓰기 가능한 폴더로 옮겨 주세요.\n\n{exc}", parent=root)
        root.destroy()
        return
    DiaryApp(root)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":
    main()
