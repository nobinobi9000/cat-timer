import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import random
import os
import sys
import time
import ctypes

def _base_dir() -> str:
    """PyInstaller --onefile 実行時は _MEIPASS、通常実行はスクリプトの場所"""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

def _exe_dir() -> str:
    """実行ファイル (.exe またはスクリプト) があるディレクトリ"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

_BASE       = _base_dir()
_SCRIPT_DIR = _exe_dir()
_IMG_DIR    = os.path.join(_BASE, "images")
if not os.path.isdir(_IMG_DIR):
    _IMG_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
_SND_DIR = os.path.join(_BASE, "sounds")


def _img_path(fname: str) -> str:
    return os.path.join(_IMG_DIR, fname)


def _snd_path(n: int) -> str:
    return os.path.join(_SND_DIR, f"alarm{n:02d}.mp3")


# ------------------------------------------------------------------
# Windows MCI 経由 MP3 再生（追加ライブラリ不要）
# ------------------------------------------------------------------
class MciPlayer:
    _winmm = ctypes.WinDLL("winmm")

    @classmethod
    def play(cls, path: str):
        cls._winmm.mciSendStringW("close alarm", None, 0, None)
        cls._winmm.mciSendStringW(f'open "{path}" type mpegvideo alias alarm', None, 0, None)
        cls._winmm.mciSendStringW("play alarm", None, 0, None)

    @classmethod
    def stop(cls):
        cls._winmm.mciSendStringW("stop alarm", None, 0, None)
        cls._winmm.mciSendStringW("close alarm", None, 0, None)


# ------------------------------------------------------------------
class CatTimer:
    BG     = "#1a1a2e"
    ACCENT = "#f97316"
    BTN_DK = "#2d2d4e"
    WHITE  = "#ffffff"
    GRAY   = "#aaaacc"
    RED    = "#8b1a1a"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ねこおじさんタイマー")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)

        _ico = os.path.join(_BASE, "cat_timer.ico")
        if os.path.exists(_ico):
            try:
                self.root.iconbitmap(_ico)
            except Exception:
                pass

        self.total_sec  = 0
        self.remain_sec = 0
        self.is_running = False
        self.is_paused  = False
        self._thread    = None

        self._alarm_no = tk.IntVar(value=1)

        self.h_var = tk.StringVar(value="00")
        self.m_var = tk.StringVar(value="25")
        self.s_var = tk.StringVar(value="00")

        self._tk_images: dict = {}
        self._random_cells: list[Image.Image] = []
        self._img_switch_id = None
        self._img_label: tk.Label | None = None

        self._load_grids()
        self._show_start()

    # ------------------------------------------------------------------
    # 4×4グリッドを 16分割してセルリストに積む
    # ------------------------------------------------------------------
    def _load_grids(self):
        grid_files = [
            "16.png",
            "grid_ojisan2.png",
            "grid_wakamono.png",
            "grid_onnano.png",
        ]
        for fname in grid_files:
            p = _img_path(fname)
            if not os.path.exists(p):
                continue
            try:
                img = Image.open(p).convert("RGBA")
                w, h = img.size
                cw, ch = w // 4, h // 4
                for row in range(4):
                    for col in range(4):
                        x0, y0 = col * cw, row * ch
                        self._random_cells.append(img.crop((x0, y0, x0 + cw, y0 + ch)))
            except Exception as e:
                print(f"[warn] {fname}: {e}")

    # ------------------------------------------------------------------
    # 汎用
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt(sec: int) -> str:
        h, r = divmod(sec, 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _clear(self):
        self._cancel_img_switch()
        for w in self.root.winfo_children():
            w.destroy()

    def _load_img(self, key: str, fname: str, size: tuple) -> ImageTk.PhotoImage | None:
        try:
            img = Image.open(_img_path(fname)).convert("RGBA")
            photo = ImageTk.PhotoImage(img.resize(size, Image.LANCZOS))
            self._tk_images[key] = photo
            return photo
        except Exception as e:
            print(f"[warn] {fname}: {e}")
            return None

    def _adjust(self, var: tk.StringVar, delta: int, maxval: int):
        try:
            val = int(var.get())
        except ValueError:
            val = 0
        var.set(f"{(val + delta) % (maxval + 1):02d}")

    def _validate_time(self, var: tk.StringVar, maxval: int, _event=None):
        try:
            val = max(0, min(int(var.get()), maxval))
        except ValueError:
            val = 0
        var.set(f"{val:02d}")

    # ------------------------------------------------------------------
    # スタート画面
    # ------------------------------------------------------------------
    def _show_start(self):
        self._clear()
        self.root.geometry("500x720")

        tk.Label(self.root, text="ねこおじさんタイマー",
                 font=("Yu Gothic UI", 18, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(pady=(16, 4))

        if photo := self._load_img("start", "start.png", (440, 293)):
            tk.Label(self.root, image=photo, bg=self.BG).pack(pady=(0, 6))

        # H : M : S
        spin = tk.Frame(self.root, bg=self.BG)
        spin.pack(pady=8)
        for i, (var, label, mx) in enumerate([
            (self.h_var, "時間", 24),
            (self.m_var, "分",   59),
            (self.s_var, "秒",   59),
        ]):
            uf = tk.Frame(spin, bg=self.BG)
            uf.grid(row=0, column=i * 2, padx=8)
            tk.Label(uf, text=label, font=("Yu Gothic UI", 10),
                     bg=self.BG, fg=self.GRAY).pack()
            tk.Button(uf, text="▲", font=("Yu Gothic UI", 12),
                      bg=self.BTN_DK, fg=self.ACCENT, bd=0, relief="flat",
                      width=4, cursor="hand2",
                      command=lambda v=var, m=mx: self._adjust(v, +1, m)).pack()
            e = tk.Entry(uf, textvariable=var,
                         font=("Consolas", 40, "bold"),
                         bg=self.BTN_DK, fg=self.WHITE,
                         insertbackground=self.WHITE,
                         bd=0, relief="flat", width=3, justify="center")
            e.pack()
            e.bind("<FocusOut>", lambda ev, v=var, m=mx: self._validate_time(v, m))
            e.bind("<Return>",   lambda ev, v=var, m=mx: self._validate_time(v, m))
            tk.Button(uf, text="▼", font=("Yu Gothic UI", 12),
                      bg=self.BTN_DK, fg=self.ACCENT, bd=0, relief="flat",
                      width=4, cursor="hand2",
                      command=lambda v=var, m=mx: self._adjust(v, -1, m)).pack()
            if i < 2:
                tk.Label(spin, text=":", font=("Consolas", 40, "bold"),
                         bg=self.BG, fg=self.WHITE).grid(row=0, column=i * 2 + 1)

        bf = tk.Frame(self.root, bg=self.BG)
        bf.pack(pady=18)
        tk.Button(bf, text="  スタート  ",
                  font=("Yu Gothic UI", 15, "bold"),
                  bg=self.ACCENT, fg="white",
                  bd=0, relief="flat", padx=22, pady=10,
                  cursor="hand2",
                  command=self._start).pack(side="left", padx=12)
        tk.Button(bf, text="⚙ 設定",
                  font=("Yu Gothic UI", 13),
                  bg=self.BTN_DK, fg=self.GRAY,
                  bd=0, relief="flat", padx=18, pady=10,
                  cursor="hand2",
                  command=self._show_settings).pack(side="left", padx=12)

    # ------------------------------------------------------------------
    # 設定画面
    # ------------------------------------------------------------------
    def _show_settings(self):
        MciPlayer.stop()
        self._clear()
        self.root.geometry("500x600")

        tk.Label(self.root, text="⚙ 設定",
                 font=("Yu Gothic UI", 18, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(pady=(20, 10))

        # ── アラーム音 ──────────────────────────────
        tk.Label(self.root, text="アラーム音",
                 font=("Yu Gothic UI", 13),
                 bg=self.BG, fg=self.WHITE).pack(anchor="w", padx=80)

        for n in range(1, 6):
            row = tk.Frame(self.root, bg=self.BG)
            row.pack(anchor="w", padx=80, pady=2)
            tk.Radiobutton(row, text=f"アラーム {n}",
                           variable=self._alarm_no, value=n,
                           font=("Yu Gothic UI", 13),
                           bg=self.BG, fg=self.WHITE,
                           selectcolor=self.BTN_DK,
                           activebackground=self.BG,
                           cursor="hand2").pack(side="left")
            tk.Button(row, text="試聴",
                      font=("Yu Gothic UI", 10),
                      bg=self.BTN_DK, fg=self.GRAY,
                      bd=0, relief="flat", padx=10, pady=3,
                      cursor="hand2",
                      command=lambda num=n: MciPlayer.play(_snd_path(num))).pack(side="left", padx=14)

        # ── キャラクター設定シート ───────────────────
        tk.Frame(self.root, bg=self.BTN_DK, height=1).pack(fill="x", padx=20, pady=(14, 10))

        tk.Label(self.root, text="キャラクター設定シート",
                 font=("Yu Gothic UI", 13),
                 bg=self.BG, fg=self.WHITE).pack(anchor="w", padx=80, pady=(0, 4))

        char_sheets = [
            ("おじさん猫", "char_ojisan.png"),
            ("わかいねこ",  "char_wakamono.png"),
            ("おんなのこねこ", "char_onnano.png"),
        ]
        for label, fname in char_sheets:
            if not os.path.exists(_img_path(fname)):
                continue
            r = tk.Frame(self.root, bg=self.BG)
            r.pack(anchor="w", padx=80, pady=2)
            tk.Label(r, text=label,
                     font=("Yu Gothic UI", 13),
                     bg=self.BG, fg=self.WHITE, width=12, anchor="w").pack(side="left")
            tk.Button(r, text="表示する",
                      font=("Yu Gothic UI", 11),
                      bg=self.BTN_DK, fg=self.ACCENT,
                      bd=0, relief="flat", padx=14, pady=4,
                      cursor="hand2",
                      command=lambda f=fname: self._show_char_popup(f)).pack(side="left", padx=14)

        # ── ねこおじさんの詳細設定 ──────────────────
        tk.Frame(self.root, bg=self.BTN_DK, height=1).pack(fill="x", padx=20, pady=(12, 10))

        row16a = tk.Frame(self.root, bg=self.BG)
        row16a.pack(anchor="w", padx=80, pady=4)
        tk.Label(row16a, text="ねこおじさんの詳細設定",
                 font=("Yu Gothic UI", 13),
                 bg=self.BG, fg=self.WHITE).pack(side="left")
        tk.Button(row16a, text="表示する",
                  font=("Yu Gothic UI", 11),
                  bg=self.BTN_DK, fg=self.ACCENT,
                  bd=0, relief="flat", padx=14, pady=4,
                  cursor="hand2",
                  command=self._show_16a_popup).pack(side="left", padx=14)

        # ── 戻る ────────────────────────────────────
        tk.Button(self.root, text="← 戻る",
                  font=("Yu Gothic UI", 13),
                  bg=self.BTN_DK, fg=self.GRAY,
                  bd=0, relief="flat", padx=20, pady=8,
                  cursor="hand2",
                  command=lambda: [MciPlayer.stop(), self._show_start()]).pack(pady=14)

    def _show_16a_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("ねこおじさんの詳細設定")
        popup.configure(bg=self.BG)
        popup.resizable(False, False)
        popup.attributes("-topmost", True)

        try:
            img = Image.open(_img_path("16a.png")).convert("RGBA")
            # 画面の 85% に収まるサイズで表示
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
            max_w = int(sw * 0.85)
            max_h = int(sh * 0.85)
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._tk_images["16a_popup"] = photo
            lbl = tk.Label(popup, image=photo, bg=self.BG, cursor="hand2")
            lbl.pack()
            lbl.bind("<Button-1>", lambda e: popup.destroy())
        except Exception as ex:
            tk.Label(popup, text=f"読み込みエラー: {ex}",
                     bg=self.BG, fg=self.WHITE,
                     font=("Yu Gothic UI", 12)).pack(padx=20, pady=20)

        tk.Label(popup, text="クリックで閉じる",
                 font=("Yu Gothic UI", 9), bg=self.BG, fg=self.GRAY).pack(pady=4)

        # 画面中央に配置
        popup.update_idletasks()
        x = (popup.winfo_screenwidth()  - popup.winfo_width())  // 2
        y = (popup.winfo_screenheight() - popup.winfo_height()) // 2
        popup.geometry(f"+{x}+{y}")

    def _show_char_popup(self, fname: str):
        popup = tk.Toplevel(self.root)
        popup.title("キャラクター設定")
        popup.configure(bg=self.BG)
        popup.resizable(False, False)
        popup.attributes("-topmost", True)

        try:
            img = Image.open(_img_path(fname)).convert("RGBA")
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
            img.thumbnail((int(sw * 0.85), int(sh * 0.85)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._tk_images[f"popup_{fname}"] = photo
            lbl = tk.Label(popup, image=photo, bg=self.BG, cursor="hand2")
            lbl.pack()
            lbl.bind("<Button-1>", lambda e: popup.destroy())
        except Exception as ex:
            tk.Label(popup, text=f"読み込みエラー: {ex}",
                     bg=self.BG, fg=self.WHITE,
                     font=("Yu Gothic UI", 12)).pack(padx=20, pady=20)

        tk.Label(popup, text="クリックで閉じる",
                 font=("Yu Gothic UI", 9), bg=self.BG, fg=self.GRAY).pack(pady=4)

        popup.update_idletasks()
        x = (popup.winfo_screenwidth()  - popup.winfo_width())  // 2
        y = (popup.winfo_screenheight() - popup.winfo_height()) // 2
        popup.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # カウント開始
    # ------------------------------------------------------------------
    def _start(self):
        total = (int(self.h_var.get()) * 3600
                 + int(self.m_var.get()) * 60
                 + int(self.s_var.get()))
        if total == 0:
            return
        self.total_sec  = total
        self.remain_sec = total
        self.is_running = True
        self.is_paused  = False
        self._show_running()
        self._thread = threading.Thread(target=self._countdown, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------
    # カウント中画面
    # ------------------------------------------------------------------
    def _show_running(self):
        self._clear()
        self.root.geometry("500x590")

        tk.Label(self.root, text="ねこおじさんタイマー",
                 font=("Yu Gothic UI", 14, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(pady=(14, 2))

        self._clock_var = tk.StringVar(value=self._fmt(self.remain_sec))
        tk.Label(self.root, textvariable=self._clock_var,
                 font=("Consolas", 68, "bold"),
                 bg=self.BG, fg=self.WHITE).pack(pady=(4, 2))

        self._prog_var = tk.DoubleVar(value=100.0)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Cat.Horizontal.TProgressbar",
                        troughcolor=self.BTN_DK,
                        background=self.ACCENT,
                        thickness=16)
        ttk.Progressbar(self.root, variable=self._prog_var,
                        style="Cat.Horizontal.TProgressbar",
                        length=420, maximum=100).pack(pady=(2, 6))

        # 常時ランダム画像
        self._img_label = tk.Label(self.root, bg=self.BG)
        self._img_label.pack(pady=4)
        self._switch_image()

        bf = tk.Frame(self.root, bg=self.BG)
        bf.pack(pady=10)
        self._pause_btn = tk.Button(bf, text="一時停止",
                                    font=("Yu Gothic UI", 13),
                                    bg=self.BTN_DK, fg=self.WHITE,
                                    bd=0, relief="flat", padx=22, pady=9,
                                    cursor="hand2",
                                    command=self._toggle_pause)
        self._pause_btn.pack(side="left", padx=12)
        tk.Button(bf, text="停止（リセット）",
                  font=("Yu Gothic UI", 13),
                  bg=self.RED, fg="white",
                  bd=0, relief="flat", padx=22, pady=9,
                  cursor="hand2",
                  command=self._stop_reset).pack(side="left", padx=12)

    # ------------------------------------------------------------------
    # 画像切り替え（8〜15秒間隔）
    # ------------------------------------------------------------------
    def _switch_image(self):
        if not self._random_cells or self._img_label is None:
            return
        cell = random.choice(self._random_cells).resize((380, 253), Image.LANCZOS)
        photo = ImageTk.PhotoImage(cell)
        self._tk_images["running"] = photo
        self._img_label.config(image=photo)
        interval_ms = random.randint(8_000, 15_000)
        self._img_switch_id = self.root.after(interval_ms, self._switch_image)

    def _cancel_img_switch(self):
        if self._img_switch_id is not None:
            try:
                self.root.after_cancel(self._img_switch_id)
            except Exception:
                pass
            self._img_switch_id = None
        self._img_label = None

    # ------------------------------------------------------------------
    # 一時停止 / 停止
    # ------------------------------------------------------------------
    def _toggle_pause(self):
        if self.is_paused:
            self.is_paused  = False
            self.is_running = True
            self._pause_btn.config(text="一時停止")
            self._thread = threading.Thread(target=self._countdown, daemon=True)
            self._thread.start()
        else:
            self.is_paused  = True
            self.is_running = False
            self._pause_btn.config(text="再開")

    def _stop_reset(self):
        self.is_running = False
        self.is_paused  = False
        self.root.after(100, self._show_start)

    # ------------------------------------------------------------------
    # カウントダウンスレッド
    # ------------------------------------------------------------------
    def _countdown(self):
        while self.remain_sec > 0 and self.is_running:
            time.sleep(1)
            if not self.is_running:
                return
            self.remain_sec -= 1
            self.root.after(0, self._update_display)

        if self.remain_sec == 0 and self.is_running:
            self.root.after(0, self._show_finish)

    def _update_display(self):
        if hasattr(self, "_clock_var"):
            self._clock_var.set(self._fmt(self.remain_sec))
        if hasattr(self, "_prog_var") and self.total_sec > 0:
            self._prog_var.set(self.remain_sec / self.total_sec * 100)

    # ------------------------------------------------------------------
    # 終了画面
    # ------------------------------------------------------------------
    def _show_finish(self):
        self.is_running = False
        self._clear()
        self.root.geometry("500x660")

        tk.Label(self.root, text="お時間です。",
                 font=("Yu Gothic UI", 36, "bold"),
                 bg=self.BG, fg=self.ACCENT).pack(pady=(32, 8))

        if photo := self._load_img("finish", "finish.png", (440, 293)):
            tk.Label(self.root, image=photo, bg=self.BG).pack(pady=8)

        bf = tk.Frame(self.root, bg=self.BG)
        bf.pack(pady=24)
        tk.Button(bf, text="もう一度",
                  font=("Yu Gothic UI", 13, "bold"),
                  bg=self.ACCENT, fg="white",
                  bd=0, relief="flat", padx=24, pady=10,
                  cursor="hand2",
                  command=lambda: [MciPlayer.stop(), self._show_start()]).pack(side="left", padx=12)
        tk.Button(bf, text="閉じる",
                  font=("Yu Gothic UI", 13),
                  bg=self.BTN_DK, fg=self.WHITE,
                  bd=0, relief="flat", padx=24, pady=10,
                  cursor="hand2",
                  command=lambda: [MciPlayer.stop(), self.root.destroy()]).pack(side="left", padx=12)

        path = _snd_path(self._alarm_no.get())
        if os.path.exists(path):
            threading.Thread(target=lambda: MciPlayer.play(path), daemon=True).start()


# ------------------------------------------------------------------
if __name__ == "__main__":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "nobi-labo.cat-timer.1.0"
        )
    except Exception:
        pass

    root = tk.Tk()
    CatTimer(root)
    root.mainloop()
