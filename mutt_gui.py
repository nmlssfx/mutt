#!/usr/bin/env python3
"""Mutt — мульти-бэкенд TTS генератор со встроенным плеером."""

from __future__ import annotations
import logging, os, sys, threading
from io import BytesIO
from pathlib import Path

import pygame, requests, webbrowser
import ttkbootstrap as ttk
from PIL import Image, ImageTk
from tkinter import filedialog
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.widgets.scrolled import ScrolledText

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path: sys.path.insert(0, str(_HERE))

# ── URLs получения ключей ──
GET_KEY_URLS = {
    "mimo": "https://platform.xiaomimimo.com/console/api-keys",
    "openrouter": "https://openrouter.ai/settings/keys",
    "groq": "https://console.groq.com/keys",
    "openai": "https://platform.openai.com/api-keys",
    "elevenlabs": "https://elevenlabs.io/app/settings/api-keys",
    "mistral": "https://console.mistral.ai/api-keys/",
}

from mutt import (
    BACKENDS, BACKEND_MIMO, BACKEND_OPENROUTER, BACKEND_GROQ,
    MIMO_VOICES, __version__,
    MIMO_STYLE_CATEGORIES, MIMO_AUDIO_TAGS,
    OR_MODEL_CHOICES, OR_MODEL_IDS, get_voices_for_model, get_model_info,
    OPENAI_VOICES, ELEVENLABS_VOICES, MISTRAL_VOICES,
    GROQ_VOICES, GROQ_VOICES_EN, GROQ_VOICES_AR,
    ELEVENLABS_DEFAULT_VOICE, ELEVENLABS_DEFAULT_MODEL,
    TTSConfig, resolve_base_url, synthesize_preview, estimate_cost,
)
from presets import get_mimo_text, get_or_text

# ── logs ──
LOG, SLOG = _HERE / "mutt.log", _HERE / "session.log"
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.FileHandler(LOG, encoding="utf-8", mode="a")])
logger = logging.getLogger("gui")
_sl = logging.getLogger("session"); _sl.setLevel(logging.INFO)
_sh = logging.FileHandler(SLOG, encoding="utf-8", mode="a"); _sh.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
_sl.addHandler(_sh)

def _fmt_size(b):
    for u in ("B", "KB", "MB"):
        if b < 1024: return f"{b:.0f}{u}"
        b /= 1024
    return f"{b:.1f}GB"
def _fmt_time(s):
    m, s = divmod(int(s), 60); return f"{m:02d}:{s:02d}"
def _font(sz=10, b=False):
    return (".AppleSystemUIFontBold" if b else ".AppleSystemUIFont", sz) if sys.platform == "darwin" else ("Segoe UI", sz, "bold" if b else "normal")
def _mono(sz=9): return ("SF Mono", sz) if sys.platform == "darwin" else ("Consolas", sz)

# ── base64 icons ──
_ICONS = {}
for name, url, fn in [
    ("mimo", "https://platform.xiaomimimo.com/static/favicon.874c9507.png", ""),
    ("or", "https://openrouter.ai/favicon.ico", ""),
]:
    try:
        r = requests.get(url, timeout=10)
        img = Image.open(BytesIO(r.content)).resize((18, 18), Image.LANCZOS)
        _ICONS[name] = ImageTk.PhotoImage(img)
    except: pass

class LogHandler(logging.Handler):
    def __init__(self, w):
        super().__init__(); self.w = w
        self.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    def emit(self, r):
        try: self.w.insert(END, self.format(r) + "\n"); self.w.see(END)
        except: pass

class Player(ttk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, **kw)
        self._file = None; self._dur = 0.0; self._play = False; self._pid = None
        if not pygame.mixer.get_init():
            try: pygame.mixer.init(frequency=24000, size=-16, channels=1)
            except: pass
        self.columnconfigure(2, weight=1)
        self.pb = ttk.Button(self, text="▶", width=3, command=self._toggle, bootstyle="success")
        self.pb.grid(row=0, column=0, padx=(0, 2))
        ttk.Button(self, text="■", width=3, command=self._stop, bootstyle="secondary").grid(row=0, column=1, padx=(0, 6))
        self.sv = ttk.DoubleVar(value=0)
        ttk.Scale(self, from_=0, to=100, variable=self.sv, bootstyle="warning", command=self._seek).grid(row=0, column=2, sticky=EW, padx=(0, 6))
        self.tv = ttk.StringVar(value="00:00 / 00:00")
        ttk.Label(self, textvariable=self.tv, font=_mono(9), width=16).grid(row=0, column=3, padx=(0, 8))
        ttk.Label(self, text="🔊", font=_mono(8)).grid(row=0, column=4)
        self.vv = ttk.DoubleVar(value=0.7)
        ttk.Scale(self, from_=0, to=1, variable=self.vv, bootstyle="info", length=60, command=lambda v: pygame.mixer.music.set_volume(float(v))).grid(row=0, column=5)
        self.fl = ttk.Label(self, text="Нет аудио", font=_font(8), bootstyle="secondary")
        self.fl.grid(row=1, column=0, columnspan=6, sticky=W, pady=(2, 0))
        self._set_en(False)
    def _set_en(self, on):
        s = NORMAL if on else DISABLED; self.pb.config(state=s)
    def load(self, p):
        self._stop_poll(); pygame.mixer.music.stop(); pygame.mixer.music.unload()
        self._file = Path(p)
        try:
            pygame.mixer.music.load(str(self._file))
            self._dur = pygame.mixer.Sound(str(self._file)).get_length()
        except: self._dur = 0
        self._play = False; self.pb.config(text="▶"); self.sv.set(0)
        self.tv.set(f"00:00 / {_fmt_time(self._dur)}")
        self.fl.config(text=f"📄 {self._file.name} ({_fmt_size(self._file.stat().st_size)})")
        self._set_en(True)
    def _toggle(self):
        if self._play: pygame.mixer.music.pause(); self._play = False; self.pb.config(text="▶"); return
        if not self._file: return
        pygame.mixer.music.set_volume(self.vv.get())
        try: pygame.mixer.music.play()
        except: return
        self._play = True; self.pb.config(text="⏸"); self._start_poll()
    def _stop(self):
        self._stop_poll(); pygame.mixer.music.stop(); self._play = False
        self.pb.config(text="▶"); self.sv.set(0); self.tv.set(f"00:00 / {_fmt_time(self._dur)}")
    def _seek(self, val):
        if self._dur <= 0: return
        pos = float(val) / 100 * self._dur
        self.tv.set(f"{_fmt_time(pos)} / {_fmt_time(self._dur)}")
    def _start_poll(self):
        self._stop_poll(); self._pid = self.after(200, self._poll)
    def _poll(self):
        if not self._play or not self.winfo_exists(): return
        busy = pygame.mixer.music.get_busy()
        pos = max(pygame.mixer.music.get_pos() / 1000, 0)
        if self._dur > 0:
            self.sv.set(min(pos / self._dur * 100, 100))
            self.tv.set(f"{_fmt_time(pos)} / {_fmt_time(self._dur)}")
        if not busy:
            self._play = False; self.pb.config(text="▶"); self.sv.set(100); return
        self._pid = self.after(200, self._poll)
    def _stop_poll(self):
        if self._pid:
            try: self.after_cancel(self._pid)
            except: pass; self._pid = None
    def destroy(self):
        self._stop_poll(); pygame.mixer.music.stop(); super().destroy()

class MuttApp(ttk.Window):
    def __init__(self):
        super().__init__(title=f"Mutt TTS v{__version__}", themename="cyborg", size=(1020, 860))
        self.minsize(820, 640)
        self._edited = False
        self._running = False
        self._cancel = False
        self._prev = None
        self._build(); self._log()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    def _build(self):
        self.columnconfigure(0, weight=7); self.columnconfigure(1, weight=3); self.rowconfigure(1, weight=1)
        f, m = _font, _mono
        # Header
        h = ttk.Frame(self)
        h.grid(row=0, column=0, columnspan=2, padx=12, pady=4, sticky=EW)
        ttk.Label(h, text=f"🎙 Mutt", font=f(20, True)).pack(side=LEFT)
        ttk.Label(h, text=f"v{__version__}", font=f(9), bootstyle="secondary").pack(side=LEFT, padx=4)
        ttk.Label(h, text="MiMo · OpenRouter", font=f(9), bootstyle="secondary").pack(side=LEFT, padx=12)
        # Left: Text
        lf = ttk.Frame(self)
        lf.grid(row=1, column=0, padx=12, pady=4, sticky=NSEW)
        lf.columnconfigure(0, weight=1); lf.rowconfigure(0, weight=1)
        tx = ttk.Labelframe(lf, text="📝 Текст", padding=6)
        tx.grid(row=0, column=0, sticky=NSEW, pady=(0, 4))
        tx.columnconfigure(0, weight=1); tx.rowconfigure(0, weight=1)
        self.txt = ScrolledText(tx, height=9, wrap=WORD, font=f(11), bootstyle="info", padding=8)
        self.txt.grid(row=0, column=0, sticky=NSEW)
        self.txt.text.insert("1.0", get_or_text())
        self.txt.text.bind("<Key>", lambda e: setattr(self, '_edited', True), add="+")
        self.txt.text.bind("<KeyRelease>", self._update_cost, add="+")
        self._edited = False
        # Cost indicator
        self.cost_var = ttk.StringVar(value="— симв. · —")
        ttk.Label(tx, textvariable=self.cost_var, font=_mono(8), bootstyle="secondary",
                  anchor=E).grid(row=1, column=0, sticky=EW, pady=(1, 0))
        # Tags
        self.tags = ttk.Labelframe(lf, text="🔊 Аудио-теги (MiMo)", padding=6)
        self.tags.grid(row=1, column=0, sticky=EW, pady=(0, 4))
        tb = ttk.Frame(self.tags); tb.grid(sticky=EW)
        for t in MIMO_AUDIO_TAGS:
            ttk.Button(tb, text=t["label"], command=lambda x=t: self.txt.text.insert(self.txt.text.index(INSERT) if 1 else "end", x["tag"]),
                       bootstyle="info-outline", width=12).pack(side=LEFT, padx=1, pady=1)
        # Context
        cx = ttk.Labelframe(lf, text="💬 Контекст (role=user)", padding=6)
        cx.grid(row=2, column=0, sticky=EW)
        self.ctx = ttk.Entry(cx, font=f(10))
        self.ctx.pack(fill=X, pady=(2, 0))
        self.ctx.insert(0, "Скажи это максимально выразительно.")
        self.ctx_lbl = ttk.Label(cx, text="", font=f(8), bootstyle="secondary")
        self.ctx_lbl.pack(anchor=W)
        # Right
        rf = ttk.Frame(self)
        rf.grid(row=1, column=1, padx=12, pady=4, sticky=NSEW)
        # ── Backend ──
        be = ttk.Labelframe(rf, text="🔀 Бэкенд", padding=6)
        be.pack(fill=X, pady=(0, 6))
        br = ttk.Frame(be); br.pack(fill=X)
        self.bic = ttk.Label(br, text=""); self.bic.pack(side=LEFT, padx=(0, 4))
        self.bv = ttk.StringVar(value=list(BACKENDS.values())[0])
        ttk.Combobox(br, textvariable=self.bv, values=list(BACKENDS.values()),
                     bootstyle="info", state="readonly", width=38).pack(side=LEFT, fill=X, expand=True)
        # MiMo auth
        self.ma = ttk.Labelframe(rf, text="🔑 MiMo", padding=6)
        r1 = ttk.Frame(self.ma); r1.pack(fill=X)
        ttk.Label(r1, text="Ключ:", font=f(9, True)).pack(side=LEFT)
        self.mk = ttk.Entry(r1, font=m(8), show="*"); self.mk.pack(side=LEFT, fill=X, expand=True, padx=4)
        self.mk.insert(0, os.environ.get("MIMO_API_KEY", ""))
        self._bind_paste(self.mk)
        ttk.Button(r1, text="🔗", width=3, bootstyle="info-outline",
                   command=lambda: webbrowser.open(GET_KEY_URLS["mimo"])).pack(side=LEFT, padx=(0, 4))
        self.mi = ttk.Label(self.ma, text="", font=f(8), bootstyle="secondary")
        self.mi.pack(anchor=W, pady=(2, 0))
        self.mk.bind("<KeyRelease>", lambda e: self._upd_mimo())
        self._upd_mimo()
        # OR auth
        self.oa = ttk.Labelframe(rf, text="🔑 OpenRouter", padding=6)
        r2 = ttk.Frame(self.oa); r2.pack(fill=X)
        ttk.Label(r2, text="Ключ:", font=f(9, True)).pack(side=LEFT)
        self.ok = ttk.Entry(r2, font=m(8), show="*"); self.ok.pack(side=LEFT, fill=X, expand=True, padx=4)
        self.ok.insert(0, os.environ.get("OPENROUTER_API_KEY", ""))
        self._bind_paste(self.ok)
        ttk.Button(r2, text="🔗", width=3, bootstyle="info-outline",
                   command=lambda: webbrowser.open(GET_KEY_URLS["openrouter"])).pack(side=LEFT, padx=(0, 4))
        ttk.Label(r2, text="Модель:", font=f(9, True)).pack(side=LEFT, padx=(8, 4))
        self.om = ttk.Combobox(r2, values=OR_MODEL_CHOICES, bootstyle="info", state="readonly", width=42)
        self.om.set(OR_MODEL_CHOICES[0]); self.om.pack(side=LEFT)
        self.oi = ttk.Label(self.oa, text="", font=f(8), bootstyle="info")
        self.oi.pack(anchor=W, pady=(2, 0))
        # Groq auth
        self.gf = ttk.Labelframe(rf, text="⚡ Groq", padding=6)
        r3 = ttk.Frame(self.gf); r3.pack(fill=X)
        ttk.Label(r3, text="Ключ:", font=f(9, True)).pack(side=LEFT)
        self.gk = ttk.Entry(r3, font=m(8), show="*"); self.gk.pack(side=LEFT, fill=X, expand=True, padx=4)
        self.gk.insert(0, os.environ.get("GROQ_API_KEY", ""))
        self._bind_paste(self.gk)
        ttk.Button(r3, text="🔗", width=3, bootstyle="info-outline",
                   command=lambda: webbrowser.open(GET_KEY_URLS["groq"])).pack(side=LEFT, padx=(0, 4))
        r3b = ttk.Frame(self.gf); r3b.pack(fill=X, pady=(2, 0))
        ttk.Label(r3b, text="Модель:", font=f(9, True)).pack(side=LEFT)
        self.gm = ttk.Combobox(r3b, values=["Orpheus English", "Orpheus Arabic Saudi"],
                                bootstyle="info", state="readonly", width=26)
        self.gm.set("Orpheus English"); self.gm.pack(side=LEFT, padx=(0, 8))
        self.gm.bind("<<ComboboxSelected>>", self._on_gm)
        ttk.Label(r3b, text="Голос:", font=f(9, True)).pack(side=LEFT)
        self.gv = ttk.Combobox(r3b, values=list(GROQ_VOICES_EN.keys()),
                                bootstyle="info", state="readonly", width=18)
        self.gv.set("Troy (муж.)"); self.gv.pack(side=LEFT)
        ttk.Label(self.gf, text="💡 $22/1M симв. · макс 200 символов · ТОЛЬКО WAV",
                  font=f(8), bootstyle="info").pack(anchor=W, pady=(2, 0))
        # OpenAI direct auth
        self.of = ttk.Labelframe(rf, text="🤖 OpenAI TTS", padding=6)
        r4 = ttk.Frame(self.of); r4.pack(fill=X)
        ttk.Label(r4, text="Ключ:", font=f(9, True)).pack(side=LEFT)
        self.oak = ttk.Entry(r4, font=m(8), show="*"); self.oak.pack(side=LEFT, fill=X, expand=True, padx=4)
        self.oak.insert(0, os.environ.get("OPENAI_API_KEY", ""))
        self._bind_paste(self.oak)
        ttk.Button(r4, text="🔗", width=3, bootstyle="info-outline",
                   command=lambda: webbrowser.open(GET_KEY_URLS["openai"])).pack(side=LEFT, padx=(0, 4))
        r4b = ttk.Frame(self.of); r4b.pack(fill=X, pady=(2, 0))
        ttk.Label(r4b, text="Голос:", font=f(9, True)).pack(side=LEFT)
        self.oav = ttk.Combobox(r4b, values=list(OPENAI_VOICES.keys()), bootstyle="info", state="readonly", width=26)
        self.oav.set("Alloy (нейтр.)"); self.oav.pack(side=LEFT)
        ttk.Label(self.of, text="💡 tts-1 · $15/1M символов", font=f(8), bootstyle="info").pack(anchor=W, pady=(2, 0))
        # ElevenLabs auth
        self.ef = ttk.Labelframe(rf, text="🗣 ElevenLabs", padding=6)
        el_row = ttk.Frame(self.ef); el_row.pack(fill=X)
        ttk.Label(el_row, text="Ключ:", font=f(9, True)).pack(side=LEFT)
        self.ek = ttk.Entry(el_row, font=m(8), show="*"); self.ek.pack(side=LEFT, fill=X, expand=True, padx=4)
        self.ek.insert(0, os.environ.get("ELEVENLABS_API_KEY", ""))
        self._bind_paste(self.ek)
        ttk.Button(el_row, text="🔗", width=3, bootstyle="info-outline",
                   command=lambda: webbrowser.open(GET_KEY_URLS["elevenlabs"])).pack(side=LEFT, padx=(0, 4))
        self.ev = ttk.StringVar(value=ELEVENLABS_DEFAULT_VOICE)
        ttk.Label(self.ef, text="Голос:", font=f(9, True)).pack(side=LEFT, padx=(8, 4))
        ev_list = list(ELEVENLABS_VOICES.keys())
        ttk.Combobox(self.ef, textvariable=ttk.StringVar(value=ev_list[0]), values=ev_list,
                     bootstyle="info", state="readonly", width=28).pack(side=LEFT)
        ttk.Label(self.ef, text="💡 10K кредитов/мес бесплатно", font=f(8), bootstyle="info").pack(anchor=W, pady=(2, 0))
        # Mistral auth
        self.mf = ttk.Labelframe(rf, text="🔮 Mistral Voxtral", padding=6)
        mf_row = ttk.Frame(self.mf); mf_row.pack(fill=X)
        ttk.Label(mf_row, text="Ключ:", font=f(9, True)).pack(side=LEFT)
        self.mk2 = ttk.Entry(mf_row, font=m(8), show="*"); self.mk2.pack(side=LEFT, fill=X, expand=True, padx=4)
        self.mk2.insert(0, os.environ.get("MISTRAL_API_KEY", ""))
        self._bind_paste(self.mk2)
        ttk.Button(mf_row, text="🔗", width=3, bootstyle="info-outline",
                   command=lambda: webbrowser.open(GET_KEY_URLS["mistral"])).pack(side=LEFT, padx=(0, 4))
        mfv = ttk.Frame(self.mf); mfv.pack(fill=X, pady=(2, 0))
        ttk.Label(mfv, text="Голос:", font=f(9, True)).pack(side=LEFT)
        self.mv = ttk.Combobox(mfv, values=list(MISTRAL_VOICES.keys()),
                                bootstyle="info", state="readonly", width=38)
        self.mv.set("Paul - Neutral (муж., EN)"); self.mv.pack(side=LEFT)
        ttk.Label(self.mf, text="💡 9 языков · $16/1M символов", font=f(8), bootstyle="info").pack(anchor=W, pady=(2, 0))
        # ── Voice frames (все сразу) ──
        self.ov = ttk.StringVar(value="alloy"); self.ovr = []
        self.ovf = ttk.Labelframe(rf, text="🎤 Голос (OpenRouter)", padding=6)
        self.mvf = ttk.Labelframe(rf, text="🎤 Голос (MiMo)", padding=6)
        self.mvv = ttk.StringVar(value="mimo_default")
        for d, v in MIMO_VOICES.items():
            ttk.Radiobutton(self.mvf, text=d, variable=self.mvv, value=d, bootstyle="info-toolbutton").pack(anchor=W, pady=1)
        self.mvi = ttk.Label(self.mvf, text="", font=f(8), bootstyle="secondary")
        self.mvi.pack()
        self.mvv.trace_add("write", lambda *a: self.mvi.config(text={"mimo_default":"Авто","default_zh":"Китайский","default_en":"Английский"}.get(self.mvv.get(),"")))
        self.msf = ttk.Labelframe(rf, text="🎭 Стиль (MiMo)", padding=6)
        self.svs = {}
        for c, o in MIMO_STYLE_CATEGORIES.items():
            cf = ttk.Frame(self.msf); cf.pack(fill=X, pady=1)
            ttk.Label(cf, text=f"{c}:", font=f(9, True), width=11, anchor=E).pack(side=LEFT)
            v = ttk.StringVar(value=o[0]); self.svs[c] = v
            for opt in o: ttk.Radiobutton(cf, text=opt or "—", variable=v, value=opt, bootstyle="info-toolbutton").pack(side=LEFT, padx=1)
        # ── Init models/backend ──
        self.om.bind("<<ComboboxSelected>>", self._on_m)
        self._on_m()
        self.bcb = br.winfo_children()[-1]  # combobox
        self.bcb.bind("<<ComboboxSelected>>", self._on_b)
        # ── Actions ──
        af = ttk.Frame(rf); af.pack(fill=X, pady=(4, 4))
        self.sb = ttk.Button(af, text="🎤 Синтезировать", command=self._go, bootstyle="success", width=28)
        self.sb.pack(fill=X, pady=(0, 3))
        self.pa = ttk.Frame(af)
        ttk.Button(self.pa, text="💾 Сохранить", command=self._save, bootstyle="primary", width=28).pack(fill=X, pady=(0, 2))
        ttk.Button(self.pa, text="🔄 Заново", command=self._retry, bootstyle="warning-outline", width=28).pack(fill=X)
        self.cb = ttk.Button(af, text="⏹ Отмена", command=self._cl, bootstyle="secondary", state=DISABLED)
        self.pl = Player(rf); self.pl.pack(fill=X, pady=(2, 4))
        self.pr = ttk.Progressbar(rf, mode=INDETERMINATE, bootstyle="warning-striped")
        self.pr.pack(fill=X, pady=(0, 2))
        self.sv = ttk.StringVar(value="")
        ttk.Label(rf, textvariable=self.sv, font=f(9), bootstyle="info", wraplength=280).pack(fill=X)
        self._on_b()
        lg = ttk.Labelframe(self, text="📋 Журнал", padding=4)
        lg.grid(row=2, column=0, columnspan=2, padx=12, pady=4, sticky=EW)
        self.lo = ScrolledText(lg, height=5, font=m(8), bootstyle="dark", padding=4)
        self.lo.pack(fill=BOTH, expand=False)

    def _log(self):
        self._lh = LogHandler(self.lo.text); self._lh.setLevel(logging.INFO)
        logging.getLogger("mutt").addHandler(self._lh); logging.getLogger("gui").addHandler(self._lh)

    def _upd_mimo(self, *_):
        k = self.mk.get().strip()
        if not k: self.mi.config(text="⏳ ключ не задан", bootstyle="secondary"); return
        url = resolve_base_url(k, "auto")
        label = "🔑 Token Plan" if k.startswith("tp-") else "☁️ Pay-as-you-go" if k.startswith("sk-") else "⚠ неизв."
        self.mi.config(text=f"{label}  →  {url}", bootstyle="info")

    def _bind_paste(self, entry):
        """Ctrl+V вставка с обработкой ошибок."""
        def p(e):
            try: entry.insert('insert', self.clipboard_get())
            except: pass
        entry.bind('<Control-v>', p); entry.bind('<Control-V>', p)

    def _is_mimo(self):
        return self.bv.get().startswith("🎙")

    def _get_backend_key(self) -> str:
        for k, v in BACKENDS.items():
            if v == self.bv.get():
                return k
        return BACKEND_MIMO

    def _on_b(self, *_):
        bk = self._get_backend_key()
        # Скрыть всё
        for w in (self.ma, self.oa, self.gf, self.of, self.ef, self.mf,
                  self.mvf, self.msf, self.ovf):
            w.pack_forget()
        self.tags.grid_remove()
        self.ctx.config(state=DISABLED); self.ctx_lbl.config(text="💡 только для MiMo / ElevenLabs")

        # Показать нужное
        if bk == BACKEND_MIMO:
            self.mvf.pack(fill=X, pady=(0, 4))
            self.msf.pack(fill=X, pady=(0, 4))
            self.ma.pack(fill=X, pady=(0, 4), before=self.mvf)
            self.tags.grid()
            self.ctx.config(state=NORMAL); self.ctx_lbl.config(text="💡 работает")
            # Ключ из env
            if not self.mk.get(): self.mk.insert(0, os.environ.get("MIMO_API_KEY", ""))
        elif bk == BACKEND_OPENROUTER:
            self.ovf.pack(fill=X, pady=(0, 4))
            self.oa.pack(fill=X, pady=(0, 4), before=self.ovf)
            if not self.ok.get(): self.ok.insert(0, os.environ.get("OPENROUTER_API_KEY", ""))
        elif bk == BACKEND_GROQ:
            self.gf.pack(fill=X, pady=(0, 4))
            if not self.gk.get(): self.gk.insert(0, os.environ.get("GROQ_API_KEY", ""))
        elif bk == "openai":
            self.of.pack(fill=X, pady=(0, 4))
            if not self.oak.get(): self.oak.insert(0, os.environ.get("OPENAI_API_KEY", ""))
        elif bk == "elevenlabs":
            self.ef.pack(fill=X, pady=(0, 4))
            if not self.ek.get(): self.ek.insert(0, os.environ.get("ELEVENLABS_API_KEY", ""))
        elif bk == "mistral":
            self.mf.pack(fill=X, pady=(0, 4))
            if not self.mk2.get(): self.mk2.insert(0, os.environ.get("MISTRAL_API_KEY", ""))
        # Icon & text
        icons = {"mimo":"mimo","openrouter":"or","groq":"groq","openai":"openai","elevenlabs":"elevenlabs","mistral":"mistral"}
        self.bic.config(image=_ICONS.get(icons.get(bk,""), ""))
        if not self._edited:
            self.txt.text.delete("1.0", END)
            t_map = {"mimo": get_mimo_text, "openrouter": get_or_text, "groq": get_or_text,
                     "openai": get_or_text, "elevenlabs": get_or_text, "mistral": get_or_text}
            self.txt.text.insert("1.0", t_map.get(bk, get_or_text)())
            self._edited = False
        self._update_cost()
        _st = {"mimo":"🎙 MiMo: введи текст, выбери стиль",
               "openrouter":"🌐 OpenRouter: выбери модель и голос",
               "groq":"⚡ Groq: макс 200 симв., WAV, EN/AR",
               "openai":"🤖 OpenAI: 6 голосов, $15/1M симв.",
               "elevenlabs":"🗣 ElevenLabs: 8 голосов, 10K/мес",
               "mistral":"🔮 Mistral: 9 языков, $16/1M симв."}
        self.sv.set(f"💡 {_st.get(bk, 'выбери бэкенд')} → Синтезировать")

    def _on_m(self, *_):
        idx = self.om.current()
        mid = OR_MODEL_IDS[idx] if 0 <= idx < len(OR_MODEL_IDS) else OR_MODEL_IDS[0]
        for rb in self.ovr: rb.destroy()
        self.ovr.clear()
        voices = get_voices_for_model(mid)
        self.ov.set(list(voices.values())[0])
        for d, v in voices.items():
            rb = ttk.Radiobutton(self.ovf, text=d, variable=self.ov, value=v, bootstyle="info-toolbutton")
            rb.pack(anchor=W, pady=1); self.ovr.append(rb)
        info = get_model_info(mid)
        self.oi.config(text=f"💡 {info.get('price','')} · {info.get('lang','')}" if info else "")
        self._update_cost()

    def _on_gm(self, *_):
        """Обновить голоса Groq при смене модели."""
        is_en = self.gm.get() == "Orpheus English"
        voices = list(GROQ_VOICES_EN.keys()) if is_en else list(GROQ_VOICES_AR.keys())
        self.gv.config(values=voices)
        self.gv.set(voices[0])
        self._update_cost()

    def _update_cost(self, *_):
        """Обновить счётчик стоимости."""
        text = self.txt.text.get("1.0", END).strip()
        bk = self._get_backend_key()
        or_idx = self.om.current() if hasattr(self, 'om') else 0
        groq_m = self.gm.get() if hasattr(self, 'gm') else ""
        cost_str, limit_str = estimate_cost(len(text), bk, or_model_idx=or_idx, groq_model=groq_m)
        self.cost_var.set(f"📊 {len(text)} симв. · {cost_str}  |  {limit_str}")

    def _cfg(self) -> TTSConfig:
        text = self.txt.text.get("1.0", END).strip(); ctx = self.ctx.get().strip()
        bk = self._get_backend_key()
        if bk == BACKEND_MIMO:
            from mutt import MIMO_VOICES as MV
            return TTSConfig(backend=BACKEND_MIMO, api_key=self.mk.get().strip(),
                             voice=MV.get(self.mvv.get(), self.mvv.get()),
                             style=" ".join(v.get() for v in self.svs.values() if v.get()),
                             user_context=ctx, text=text, auth_mode="auto")
        if bk == BACKEND_OPENROUTER:
            idx = self.om.current()
            return TTSConfig(backend=BACKEND_OPENROUTER, or_api_key=self.ok.get().strip(),
                             or_model=OR_MODEL_IDS[idx] if 0 <= idx < len(OR_MODEL_IDS) else OR_MODEL_IDS[0],
                             or_voice=self.ov.get(), user_context=ctx, text=text)
        if bk == BACKEND_GROQ:
            model = "canopylabs/orpheus-v1-english" if self.gm.get() == "Orpheus English" else "canopylabs/orpheus-arabic-saudi"
            voice = self.gv.get()
            # Найти voice id
            all_v = {**GROQ_VOICES_EN, **GROQ_VOICES_AR}
            voice_id = all_v.get(voice, "troy")
            return TTSConfig(backend=BACKEND_GROQ, groq_api_key=self.gk.get().strip(),
                             groq_model=model, groq_voice=voice_id, user_context=ctx, text=text)
        if bk == "openai":
            voice_display = self.oav.get()
            voice_id = OPENAI_VOICES.get(voice_display, "alloy")
            return TTSConfig(backend="openai", oai_api_key=self.oak.get().strip(),
                             oai_voice=voice_id, user_context=ctx, text=text)
        if bk == "elevenlabs":
            cb = self.ef.winfo_children()[-3]  # combobox
            if hasattr(cb, 'get'):
                v = ELEVENLABS_VOICES.get(cb.get(), ELEVENLABS_DEFAULT_VOICE) if cb.get() else ELEVENLABS_DEFAULT_VOICE
            else: v = ELEVENLABS_DEFAULT_VOICE
            return TTSConfig(backend="elevenlabs", el_api_key=self.ek.get().strip(),
                             el_voice=v, user_context=ctx, text=text)
        if bk == "mistral":
            voice_id = MISTRAL_VOICES.get(self.mv.get(), list(MISTRAL_VOICES.values())[0])
            return TTSConfig(backend="mistral", mistral_api_key=self.mk2.get().strip(),
                             mistral_voice=voice_id, user_context=ctx, text=text)
        return TTSConfig(backend=BACKEND_MIMO, text=text)

    def _go(self):
        if self._running: return
        cfg = self._cfg()
        if not cfg.text: Messagebox.show_warning("Введите текст.", ""); return
        bk = cfg.backend
        errors = {BACKEND_MIMO: (cfg.api_key, "MiMo"), BACKEND_OPENROUTER: (cfg.or_api_key, "OpenRouter"),
                  BACKEND_GROQ: (cfg.groq_api_key, "Groq"), "openai": (cfg.oai_api_key, "OpenAI"),
                  "elevenlabs": (cfg.el_api_key, "ElevenLabs"), "mistral": (cfg.mistral_api_key, "Mistral")}
        need_key, name = errors.get(bk, (None, ""))
        if need_key is not None and not need_key:
            Messagebox.show_error(f"Нет ключа {name}.", ""); return
        self._running = True; self._cancel = False
        self.sb.pack_forget(); self.cb.pack(fill=X, pady=(0, 3)); self.cb.config(state=NORMAL)
        self.pr.start(10); self.sv.set("🎤 Синтезирую…")
        threading.Thread(target=self._wrk, args=(cfg,), daemon=True).start()
    def _cl(self):
        if self._running: self._cancel = True; self.sv.set("⏳ Отмена…")
    def _save(self):
        if not getattr(self, '_prev', None) or not self._prev.exists(): Messagebox.show_error("Нет файла.", ""); return
        ext = self._prev.suffix.lower()
        p = filedialog.asksaveasfilename(defaultextension=ext, filetypes=[("WAV", "*.wav"), ("MP3", "*.mp3"), ("Все", "*.*")])
        if not p: return
        try:
            Path(p).write_bytes(self._prev.read_bytes())
            _sl.info("SAVED path=%s size=%d", p, Path(p).stat().st_size)
            Messagebox.show_info(f"Сохранено:\n{p}", "Готово")
        except Exception as e: Messagebox.show_error(str(e), "Ошибка")
    def _retry(self):
        self.pl._stop(); self._prev = None; self._running = False; self._cancel = False; self.pr.stop()
        self.sb.pack(fill=X, pady=(0, 3)); self.cb.pack_forget(); self.pa.pack_forget()
        self.sv.set("🔄 Настрой заново")
    def _wrk(self, c):
        try:
            if self._cancel: self._after(self._reset); return
            _sl.info("SYNTH backend=%s len=%d", c.backend, len(c.text))
            p = synthesize_preview(c); self._prev = p
            _sl.info("DONE path=%s size=%d", p, p.stat().st_size)
            self._after(self._done, p)
        except Exception as e:
            logger.error("❌ %s", e)
            self._after(lambda: self.sv.set(f"❌ {e}")); self._after(lambda: Messagebox.show_error(str(e), "Ошибка"))
            self._after(self._reset)
    def _done(self, p):
        self._running = False; self.pr.stop(); self._prev = p
        self.pl.load(p); self.sv.set("✅ Загружено  ▶ слушай")
        self.cb.pack_forget(); self.pa.pack(fill=X); self.sb.pack_forget()
    def _reset(self):
        self._running = False; self._cancel = False; self.pr.stop()
        self.sb.pack(fill=X, pady=(0, 3)); self.cb.pack_forget(); self.pa.pack_forget()
    def _after(self, fn, *a, **kw):
        if self.winfo_exists(): self.after(0, fn, *a, **kw)
    def destroy(self):
        if hasattr(self, '_lh'): logging.getLogger("mutt").removeHandler(self._lh)
        logging.getLogger("gui").removeHandler(self._lh) if hasattr(self, '_lh') else None
        super().destroy()


    def _on_close(self):
        """Сохранить ключи в .env и закрыть окно."""
        try:
            from pathlib import Path
            env_path = _HERE / ".env"
            lines = []
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").split("\n")
            updates = {"MIMO_API_KEY": self.mk.get().strip(),
                       "OPENROUTER_API_KEY": self.ok.get().strip(),
                       "GROQ_API_KEY": self.gk.get().strip(),
                       "OPENAI_API_KEY": self.oak.get().strip(),
                       "ELEVENLABS_API_KEY": self.ek.get().strip(),
                       "MISTRAL_API_KEY": self.mk2.get().strip()}
            for k, v in updates.items():
                if not v:
                    continue
                found = False
                for i, line in enumerate(lines):
                    if line.strip().startswith(k + "="):
                        lines[i] = f"{k}={v}"
                        found = True
                        break
                if not found:
                    lines.append(f"{k}={v}")
            if updates:
                env_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception:
            pass
        self.destroy()

if __name__ == "__main__":
    MuttApp().mainloop()
