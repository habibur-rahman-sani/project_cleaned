# -*- coding: utf-8 -*-
"""
indicator.py — "Hermes আপনার স্ক্রিন নিয়ন্ত্রণ করছে" ভিজ্যুয়াল ইন্ডিকেটর।

কেন আলাদা ফাইল: agent.py-র websocket লুপ asyncio, আলাদা থ্রেডে চলে (main()
দেখো)। কিন্তু Tkinter-এর মূল নিয়ম — Tk উইজেট শুধু যে থ্রেডে mainloop() চলছে
সেই থ্রেড থেকেই ছোঁয়া যায়। তাই এই মডিউল একটা থ্রেড-সেফ Queue রাখে: অন্য
থ্রেড (websocket লুপ) থেকে শুধু event push করা হয় (flash_click, notify_active),
আর Tk-এর নিজের `root.after()` লুপ (মূল থ্রেডে) সেই queue পড়ে আসল উইজেট
বদলায়। কোথাও সরাসরি অন্য থ্রেড থেকে Tk উইজেট ছোঁয়া হয় না।

agent.py থেকে ব্যবহার:
    controller = IndicatorController()
    threading.Thread(target=lambda: asyncio.run(run_forever(token, controller)),
                      daemon=True).start()
    controller.start()   # ব্লক করে — মূল থ্রেডে চালাতে হবে
"""
from __future__ import annotations

import queue
import tkinter as tk


class IndicatorController:
    IDLE_HIDE_MS = 2500       # এত মিলিসেকেন্ড কোনো action না এলে ব্যানার লুকিয়ে যাবে
    FLASH_MS = 400            # ক্লিক-ফ্ল্যাশ কতক্ষণ দেখাবে
    POLL_MS = 40              # queue কতবার চেক হবে

    def __init__(self) -> None:
        self._q: "queue.Queue[tuple]" = queue.Queue()
        self._root: tk.Tk | None = None
        self._banner: tk.Toplevel | None = None
        self._hide_job = None

    # ---- থ্রেড-সেফ পাবলিক API (websocket থ্রেড থেকে কল হয়) ----

    def notify_active(self, action: str) -> None:
        """যেকোনো action আসার আগে কল করো — ব্যানার দেখায়/idle-টাইমার রিসেট করে।"""
        self._q.put(("active", action))

    def flash_click(self, x: int, y: int) -> None:
        """click/drag-এর কোঅর্ডিনেটে একটা মুহূর্তের জন্য লাল বৃত্ত দেখায়।"""
        self._q.put(("flash", x, y))

    # ---- মূল থ্রেডে চালানোর জন্য ----

    def start(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()  # কোনো মূল উইন্ডো লাগবে না, শুধু ইভেন্ট-লুপের জন্য
        self._build_banner()
        self._poll()
        self._root.mainloop()

    # ---- ভেতরের (শুধু মূল থ্রেড থেকে ছোঁয়া হয়) ----

    def _build_banner(self) -> None:
        b = tk.Toplevel(self._root)
        b.overrideredirect(True)       # টাইটেল বার/বর্ডার নাই
        b.attributes("-topmost", True)
        try:
            b.attributes("-alpha", 0.92)
        except tk.TclError:
            pass
        b.configure(bg="#c62828")
        label = tk.Label(
            b, text="🔴  Hermes আপনার স্ক্রিন নিয়ন্ত্রণ করছে",
            bg="#c62828", fg="white", font=("Segoe UI", 11, "bold"),
            padx=16, pady=6,
        )
        label.pack()
        b.update_idletasks()
        w = b.winfo_reqwidth()
        sw = b.winfo_screenwidth()
        b.geometry(f"+{(sw - w) // 2}+0")  # স্ক্রিনের উপরে, মাঝ বরাবর
        b.withdraw()
        self._banner = b

    def _show_banner(self) -> None:
        if self._banner is not None:
            self._banner.deiconify()
            self._banner.lift()

    def _hide_banner(self) -> None:
        if self._banner is not None:
            self._banner.withdraw()

    def _do_flash(self, x: int, y: int) -> None:
        size = 34
        f = tk.Toplevel(self._root)
        f.overrideredirect(True)
        f.attributes("-topmost", True)
        try:
            f.attributes("-alpha", 0.75)
        except tk.TclError:
            pass
        f.geometry(f"{size}x{size}+{int(x) - size // 2}+{int(y) - size // 2}")
        canvas = tk.Canvas(f, width=size, height=size, highlightthickness=0, bg="black")
        canvas.pack()
        # কিছু প্ল্যাটফর্মে "black" কে transparent করা যায় — না গেলেও বৃত্তটা দেখাই যথেষ্ট
        try:
            f.attributes("-transparentcolor", "black")
        except tk.TclError:
            pass
        canvas.create_oval(2, 2, size - 2, size - 2, outline="#ff1744", width=3)
        self._root.after(self.FLASH_MS, f.destroy)

    def _reset_idle_timer(self) -> None:
        if self._hide_job is not None:
            self._root.after_cancel(self._hide_job)
        self._hide_job = self._root.after(self.IDLE_HIDE_MS, self._hide_banner)

    def _poll(self) -> None:
        try:
            while True:
                event = self._q.get_nowait()
                if event[0] == "active":
                    self._show_banner()
                    self._reset_idle_timer()
                elif event[0] == "flash":
                    self._do_flash(event[1], event[2])
        except queue.Empty:
            pass
        self._root.after(self.POLL_MS, self._poll)
