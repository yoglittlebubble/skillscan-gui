#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SkillSpector 体检台 —— skillspector 的图形界面外壳。

填入 GitHub 网址或本地路径，点「开始扫描」，直接看体检结果。
内部调用本机已安装的 skillspector CLI（-f json），解析后可视化。
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "SkillSpector 体检台"
APP_VERSION = "1.1"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
SEV_COLOR = {
    "CRITICAL": "#c62828",
    "HIGH": "#e65100",
    "MEDIUM": "#f9a825",
    "LOW": "#2e7d32",
    "INFO": "#546e7a",
}
REC_TEXT = {
    "SAFE": ("可以安装", "#2e7d32"),
    "CAUTION": ("谨慎使用", "#f9a825"),
    "DO_NOT_INSTALL": ("不要安装", "#c62828"),
}
EXCLUDE_GLOBS = [
    "**/tests/**",
    "**/test/**",
    "**/__tests__/**",
    "**/*.test.mjs",
    "**/*.test.js",
    "**/*.test.ts",
    "**/*.spec.js",
    "**/*.spec.mjs",
    "**/*.min.js",
]

FONT_UI = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_MONO = ("Consolas", 9)
FONT_BIG = ("Microsoft YaHei UI", 26, "bold")


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def load_config():
    """读取安装器写下的 config.json（先看程序目录，再看 LocalAppData）。"""
    cands = [
        os.path.join(app_dir(), "config.json"),
        os.path.join(os.path.dirname(app_dir()), "config.json"),  # 安装布局：app 目录的上一层
    ]
    la = os.environ.get("LOCALAPPDATA")
    if la:
        cands.append(os.path.join(la, "SkillSpector", "config.json"))
    for c in cands:
        try:
            with open(c, encoding="utf-8-sig") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def resolve_engine():
    """返回 (给人看的说明, 命令前缀)；找不到就 (None, None)。

    命令前缀后面直接接 scan 参数，所以既支持 skillspector.exe，
    也支持「便携 Python + run_engine.py」这种免安装形态。
    """
    cfg = load_config()

    py, runner = cfg.get("engine_python"), cfg.get("engine_runner")
    if py and runner and os.path.isfile(py) and os.path.isfile(runner):
        return "便携引擎：" + py, [py, runner]

    exe = cfg.get("engine_exe")
    if exe and os.path.isfile(exe):
        return exe, [exe]

    env = os.environ.get("SKILLSPECTOR_EXE")
    if env and os.path.isfile(env):
        return env, [env]

    la = os.environ.get("LOCALAPPDATA")
    if la:
        base = os.path.join(la, "SkillSpector", "engine")
        py2 = os.path.join(base, "python.exe")
        runner2 = os.path.join(base, "run_engine.py")
        if os.path.isfile(py2) and os.path.isfile(runner2):
            return "便携引擎：" + py2, [py2, runner2]

    for legacy in (
        os.path.join(app_dir(), "skillspector.exe"),
        r"D:\software\skillspector\.venv\Scripts\skillspector.exe",
        os.path.expandvars(r"%USERPROFILE%\.local\bin\skillspector.exe"),
    ):
        if os.path.isfile(legacy):
            return legacy, [legacy]

    w = shutil.which("skillspector")
    if w:
        return w, [w]
    return None, None


def port_open(host, port, timeout=0.25):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except OSError:
        return False


def parse_json_report(stdout):
    """从 stdout 里挖出 JSON 报告，容忍前后杂讯。"""
    text = stdout.strip()
    if not text:
        raise ValueError("skillspector 没有输出内容")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("输出里找不到 JSON 报告")
    return json.loads(text[start : end + 1])


def split_reports(data):
    """兼容单 skill 报告与多 skill（--recursive）聚合报告。"""
    if not isinstance(data, dict):
        return []
    if "risk_assessment" in data:
        return [data]
    for key in ("reports", "results", "skills", "scans", "items"):
        val = data.get(key)
        if isinstance(val, list) and any(isinstance(x, dict) and "risk_assessment" in x for x in val):
            return [x for x in val if isinstance(x, dict) and "risk_assessment" in x]
    # 兜底：任何一层里出现的报告对象
    found = []

    def walk(node):
        if isinstance(node, dict):
            if "risk_assessment" in node and "skill" in node:
                found.append(node)
            else:
                for v in node.values():
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return found


def work_area(root):
    """桌面工作区（不含任务栏）：宽、高、左、上。"""
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return (rect.right - rect.left, rect.bottom - rect.top, rect.left, rect.top)
    except Exception:  # noqa: BLE001
        pass
    return (root.winfo_screenwidth(), root.winfo_screenheight(), 0, 0)


class App:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.busy = False
        self.last_report = None
        self.last_cmd = ""
        self.t0 = 0.0
        self.engine_desc, self.engine_cmd = resolve_engine()
        self.issues = []          # 当前展示的问题（列表 of dict）
        self.report_meta = {}     # 汇总信息

        root.title(f"{APP_TITLE} v{APP_VERSION}")
        aw, ah, ax, ay = work_area(root)
        w = max(1000, min(1340, aw - 40))
        h = max(620, min(920, ah - 40))
        root.geometry(f"{w}x{h}+{ax + (aw - w) // 2}+{ay + max(8, (ah - h) // 2 - 10)}")
        root.minsize(1000, 620)
        if os.environ.get("SSGUI_DEBUG"):
            try:
                root.update_idletasks()
                with open(os.path.join(os.environ.get("TEMP", "."), "ssgui.log"), "w", encoding="utf-8") as f:
                    f.write(
                        f"work_area={aw}x{ah}+{ax}+{ay} winfo={root.winfo_screenwidth()}x{root.winfo_screenheight()} "
                        f"scaling={root.tk.call('tk', 'scaling')} geom_after={root.geometry()} "
                        f"dpi={root.winfo_fpixels('1i')}\n"
                    )
            except Exception:  # noqa: BLE001
                pass
        self._setup_style()
        self._build()
        self._timer()
        self.draw_gauge(-1)

        if not self.engine_cmd:
            self.log("⚠ 没有找到扫描引擎")
            messagebox.showwarning(
                "找不到扫描引擎",
                "没有找到 skillspector 引擎。\n\n"
                "如果是别人给的安装包，请先运行压缩包里的「安装.bat」。\n\n"
                "装好后引擎会位于：\n%LOCALAPPDATA%\\SkillSpector\\engine\\\n\n"
                "也可以用环境变量 SKILLSPECTOR_EXE 指定一个 skillspector.exe。",
            )
        else:
            self.log(f"就绪 · {self.engine_desc}")

    # ---------- 样式 ----------
    def _setup_style(self):
        st = ttk.Style()
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        st.configure("TLabel", font=FONT_UI)
        st.configure("Small.TLabel", font=FONT_SMALL, foreground="#666")
        st.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"))
        st.configure("Go.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(18, 6))
        st.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        st.configure("Treeview", rowheight=26, font=FONT_SMALL)
        st.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"))

    # ---------- 布局 ----------
    def _build(self):
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # 顶部：输入
        top = ttk.Frame(root, padding=(16, 14, 16, 6))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="目标", style="Title.TLabel").grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.var_target = tk.StringVar()
        self.entry = ttk.Entry(top, textvariable=self.var_target, font=("Microsoft YaHei UI", 10))
        self.entry.grid(row=0, column=1, sticky="ew", ipady=4)
        self.entry.insert(0, "")
        self.entry.bind("<Return>", lambda e: self.start_scan())

        ttk.Button(top, text="选文件夹", command=self.browse_dir, width=9).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(top, text="选文件", command=self.browse_file, width=8).grid(row=0, column=3, padx=(6, 0))
        self.btn_go = ttk.Button(top, text="开始扫描", style="Go.TButton", command=self.start_scan)
        self.btn_go.grid(row=0, column=4, padx=(10, 0))
        self.btn_stop = ttk.Button(top, text="停止", command=self.stop_scan, state="disabled", width=6)
        self.btn_stop.grid(row=0, column=5, padx=(6, 0))

        # 选项行
        opts = ttk.Frame(root, padding=(16, 0, 16, 8))
        opts.grid(row=1, column=0, sticky="ew")
        self.var_excl = tk.BooleanVar(value=True)
        self.var_rec = tk.BooleanVar(value=False)
        self.var_llm = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="排除测试文件", variable=self.var_excl).pack(side="left")
        ttk.Checkbutton(opts, text="递归扫描子目录里的多个 skill", variable=self.var_rec).pack(side="left", padx=(14, 0))
        ttk.Checkbutton(opts, text="启用 LLM 分析（需配 API Key）", variable=self.var_llm).pack(side="left", padx=(14, 0))
        ttk.Label(opts, text="支持：GitHub 地址 · zip · 本地文件夹 · SKILL.md", style="Small.TLabel").pack(side="right")

        # 主体
        body = ttk.PanedWindow(root, orient="horizontal")
        body.grid(row=2, column=0, sticky="nsew", padx=16)

        left = ttk.Frame(body, width=270)
        body.add(left, weight=0)
        right = ttk.Frame(body)
        body.add(right, weight=1)

        # 左：分数卡
        self.card = ttk.Frame(left, style="Card.TFrame", padding=12)
        self.card.pack(fill="x", pady=(0, 10))

        ttk.Label(self.card, text="风险评分", style="Small.TLabel").pack(anchor="w")
        self.gauge = tk.Canvas(self.card, width=230, height=132, highlightthickness=0, bg="#ffffff")
        self.gauge.pack(pady=(2, 2))
        self.lbl_rec = tk.Label(self.card, text="—", font=("Microsoft YaHei UI", 12, "bold"), bg="#ffffff")
        self.lbl_rec.pack()
        self.lbl_skill = ttk.Label(self.card, text="", style="Small.TLabel", wraplength=210)
        self.lbl_skill.pack(anchor="w", pady=(8, 0))

        self.counts = {}
        cnt = ttk.Frame(left)
        cnt.pack(fill="x", pady=(0, 10))
        ttk.Label(cnt, text="问题分布", style="Small.TLabel").pack(anchor="w", pady=(0, 4))
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            row = ttk.Frame(cnt)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=sev, font=FONT_SMALL, fg="#fff", bg=SEV_COLOR[sev], width=9).pack(side="left")
            lbl = tk.Label(row, text="0", font=FONT_SMALL, anchor="w")
            lbl.pack(side="left", padx=8)
            self.counts[sev] = lbl

        self.lbl_cov = ttk.Label(left, text="", style="Small.TLabel", wraplength=250, justify="left")
        self.lbl_cov.pack(fill="x")

        # 右：过滤 + 列表
        bar = ttk.Frame(right)
        bar.pack(fill="x")
        ttk.Label(bar, text="过滤", style="Small.TLabel").pack(side="left")
        self.var_filter = tk.StringVar(value="全部级别")
        self.cbo = ttk.Combobox(
            bar, textvariable=self.var_filter, state="readonly", width=10,
            values=["全部级别", "CRITICAL", "HIGH", "MEDIUM", "LOW"],
        )
        self.cbo.pack(side="left", padx=(6, 12))
        self.cbo.bind("<<ComboboxSelected>>", lambda e: self.fill_tree())
        self.var_search = tk.StringVar()
        ttk.Label(bar, text="搜索", style="Small.TLabel").pack(side="left")
        ttk.Entry(bar, textvariable=self.var_search, width=22).pack(side="left", padx=(6, 0))
        self.var_search.trace_add("write", lambda *a: self.fill_tree())
        self.lbl_total = ttk.Label(bar, text="", style="Small.TLabel")
        self.lbl_total.pack(side="right")

        cols = ("sev", "cat", "pat", "loc")
        self.tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        for c, txt, w, anchor in (
            ("sev", "级别", 88, "center"),
            ("cat", "类别", 180, "w"),
            ("pat", "模式", 200, "w"),
            ("loc", "位置", 520, "w"),
        ):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w, anchor=anchor, stretch=(c == "loc"))
        vsb = ttk.Scrollbar(right, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(right, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        for sev, col in SEV_COLOR.items():
            self.tree.tag_configure(sev, foreground=col)

        # 详情
        self.detail = tk.Text(root, height=9, wrap="word", font=FONT_SMALL, relief="solid", borderwidth=1,
                              bg="#fbfbfb", padx=10, pady=8, state="disabled")
        self.detail.tag_configure("h", font=("Microsoft YaHei UI", 10, "bold"), spacing1=6)
        self.detail.tag_configure("mono", font=FONT_MONO, background="#f0f0f0", lmargin1=8, lmargin2=8)
        self.detail.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 6))
        self._set_detail("选中上方任意问题，这里显示详情。")

        # 状态栏
        foot = ttk.Frame(root, padding=(16, 0, 16, 10))
        foot.grid(row=4, column=0, sticky="ew")
        self.pb = ttk.Progressbar(foot, mode="indeterminate", length=140)
        self.pb.pack(side="left")
        self.lbl_status = ttk.Label(foot, text="空闲", style="Small.TLabel", width=92, anchor="w")
        self.lbl_status.pack(side="left", padx=10, fill="x", expand=True)
        self.btn_copy = ttk.Button(foot, text="复制摘要", command=self.copy_summary, state="disabled")
        self.btn_copy.pack(side="right")
        self.btn_export = ttk.Button(foot, text="导出 JSON", command=self.export_json, state="disabled")
        self.btn_export.pack(side="right", padx=(0, 6))

    # ---------- 状态 ----------
    def log(self, msg):
        msg = str(msg)
        self.lbl_status.config(text=msg if len(msg) <= 88 else msg[:85] + "…")

    def _timer(self):
        if self.busy:
            self.log(f"扫描中… {time.time() - self.t0:.0f}s")
        self.root.after(500, self._timer)

    def set_busy(self, busy):
        self.busy = busy
        self.btn_go.config(state="disabled" if busy else "normal")
        self.btn_stop.config(state="normal" if busy else "disabled")
        if busy:
            self.pb.start(12)
        else:
            self.pb.stop()

    # ---------- 输入 ----------
    def browse_dir(self):
        p = filedialog.askdirectory(title="选择 skill 文件夹")
        if p:
            self.var_target.set(os.path.normpath(p))

    def browse_file(self):
        p = filedialog.askopenfilename(
            title="选择 SKILL.md / zip",
            filetypes=[("Skill 定义或压缩包", "SKILL.md *.zip *.md"), ("所有文件", "*.*")],
        )
        if p:
            self.var_target.set(os.path.normpath(p))

    def stop_scan(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.log("已请求停止…")

    # ---------- 扫描 ----------
    def build_cmd(self, target):
        cmd = list(self.engine_cmd) + ["scan", target, "-f", "json"]
        if not self.var_llm.get():
            cmd.append("--no-llm")
        if self.var_rec.get():
            cmd += ["--recursive", "--max-skills", "64"]
        elif self.var_excl.get():
            for g in EXCLUDE_GLOBS:
                cmd += ["--exclude", g]
        return cmd

    def start_scan(self):
        if self.busy:
            return
        target = self.var_target.get().strip().strip('"')
        if not target:
            messagebox.showinfo("等一下", "先填一个 GitHub 地址或本地路径吧。")
            return
        if not self.engine_cmd:
            messagebox.showerror("找不到引擎", "没有找到扫描引擎，请先运行安装包里的「安装.bat」。")
            return
        if target.lower().startswith(("http://", "https://")) and self.var_excl.get() and not self.var_rec.get():
            pass  # 远程地址不支持 --exclude，下面统一过滤
        local = os.path.exists(target)
        if not local and not target.lower().startswith(("http://", "https://", "git@")):
            messagebox.showwarning("路径不存在", f"找不到：\n{target}\n\n也可以直接填 GitHub 网址。")
            return

        cmd = self.build_cmd(target)
        if not local:
            # 远程/压缩包不支持 --exclude，去掉
            cleaned, skip = [], False
            for i, a in enumerate(cmd):
                if skip:
                    skip = False
                    continue
                if a == "--exclude":
                    skip = True
                    continue
                cleaned.append(a)
            cmd = cleaned

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env.setdefault("PYTHONUTF8", "1")
        if port_open("127.0.0.1", 7897):
            env["HTTP_PROXY"] = "http://127.0.0.1:7897"
            env["HTTPS_PROXY"] = "http://127.0.0.1:7897"

        self.last_cmd = " ".join(cmd)
        self.t0 = time.time()
        self.set_busy(True)
        self.log("扫描中…")
        threading.Thread(target=self._worker, args=(cmd, env), daemon=True).start()

    def _worker(self, cmd, env):
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                creationflags=CREATE_NO_WINDOW,
            )
            out, err = self.proc.communicate()
            rc = self.proc.returncode
            out = out.decode("utf-8", "replace")
            err = err.decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            rc, out, err = -1, "", f"{type(e).__name__}: {e}"
        elapsed = time.time() - self.t0
        self.root.after(0, lambda: self._finish(rc, out, err, elapsed))

    def _finish(self, rc, out, err, elapsed):
        self.set_busy(False)
        if rc not in (0, 1):
            self.log(f"扫描失败（exit {rc}）")
            tail = (err or out or "").strip()[-1200:]
            messagebox.showerror("扫描失败", f"退出码 {rc}\n\n{tail or '没有更多信息'}")
            return
        try:
            data = parse_json_report(out)
        except Exception as e:  # noqa: BLE001
            self.log("报告解析失败")
            messagebox.showerror("解析失败", f"{e}\n\n输出片段：\n{out[:800]}\n{err[:400]}")
            return

        self.last_report = data
        reports = split_reports(data)
        if not reports:
            self.log("报告结构不认识")
            messagebox.showerror("解析失败", "报告里没有找到 risk_assessment 字段。")
            return

        self.render(reports, data, rc, elapsed)
        self.btn_export.config(state="normal")
        self.btn_copy.config(state="normal")

    # ---------- 渲染 ----------
    def render(self, reports, data, rc, elapsed):
        total = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        max_score = 0
        worst_rec = "SAFE"
        rows = []
        for rep in reports:
            ra = rep.get("risk_assessment") or {}
            score = ra.get("score") or 0
            max_score = max(max_score, score)
            rec = ra.get("recommendation") or "SAFE"
            if REC_TEXT.get(rec, ("", ""))[1] == "#c62828":
                worst_rec = "DO_NOT_INSTALL"
            elif rec == "CAUTION" and worst_rec == "SAFE":
                worst_rec = "CAUTION"
            skill = (rep.get("skill") or {}).get("name") or "skill"
            for iss in rep.get("issues") or []:
                sev = (iss.get("severity") or "INFO").upper()
                total[sev] = total.get(sev, 0) + 1
                loc = iss.get("location") or {}
                rows.append({
                    "skill": skill,
                    "sev": sev,
                    "cat": iss.get("category") or "",
                    "pat": iss.get("pattern") or iss.get("id") or "",
                    "file": loc.get("file") or "",
                    "line": loc.get("start_line"),
                    "raw": iss,
                })

        rows.sort(key=lambda r: (SEV_ORDER.get(r["sev"], 9), r["skill"], r["file"]))
        self.issues = rows

        multi = len(reports) > 1
        self.multi = multi
        self.draw_gauge(max_score)
        label, color = REC_TEXT.get(worst_rec, ("未知", "#546e7a"))
        self.lbl_rec.config(text=label, fg=color)
        names = sorted({(r.get("skill") or {}).get("name") or "skill" for r in reports})
        shown = "、".join(names[:3]) + ("…" if len(names) > 3 else "")
        self.lbl_skill.config(text=("共 %d 个 skill：%s" % (len(reports), shown)) if multi else (names[0] if names else ""))

        for sev, lbl in self.counts.items():
            lbl.config(text=str(total.get(sev, 0)), fg=SEV_COLOR.get(sev, "#333"))

        cov = data.get("analysis_completeness") or (reports[0].get("analysis_completeness") or {})
        bits = []
        if cov.get("coverage_percent") is not None:
            status_cn = {"complete": "完整", "partial": "部分检视", "incomplete": "不完整"}.get(
                str(cov.get("status", "")).lower(), cov.get("status", "")
            )
            bits.append(f"覆盖率 {cov['coverage_percent']}%（{status_cn}）")
        sup = data.get("suppressed_count")
        if sup:
            bits.append(f"已按基线压制 {sup} 条")
        bits.append("离线载入" if elapsed is None else f"用时 {elapsed:.1f}s")
        self.lbl_cov.config(text=" ｜ ".join(bits))

        self.fill_tree()
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])
            self.tree.focus(kids[0])
            self.on_select()
        self.log(f"完成 · 评分 {max_score}/100 · {len(rows)} 条问题 · exit {rc}")

    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        f = self.var_filter.get()
        q = self.var_search.get().strip().lower()
        n = 0
        for r in self.issues:
            if f != "全部级别" and r["sev"] != f:
                continue
            loc = r["file"] + (f":{r['line']}" if r["line"] else "")
            if q and q not in (r["cat"] + r["pat"] + loc + r["raw"].get("finding", "")).lower():
                continue
            loc_disp = f"[{r['skill']}] {loc}" if getattr(self, "multi", False) else loc
            self.tree.insert("", "end", iid=str(id(r)), values=(r["sev"], r["cat"], r["pat"], loc_disp),
                             tags=(r["sev"],))
            r["_iid"] = str(id(r))
            n += 1
        self.lbl_total.config(text=f"显示 {n} / 共 {len(self.issues)} 条")

    def on_select(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        iid = sel[0]
        for r in self.issues:
            if r.get("_iid") == iid:
                self.show_issue(r)
                return

    def show_issue(self, r):
        raw = r["raw"]
        conf = raw.get("confidence")
        lines = [
            f"{r['sev']} · {r['cat']} · {r['pat']}",
            f"位置：{r['file']}:{r['line'] or '?'}" + (f"   置信度：{conf:.0%}" if isinstance(conf, (int, float)) else ""),
            "",
        ]
        if raw.get("finding"):
            lines += ["问题片段", str(raw["finding"]).strip()[:1500], ""]
        if raw.get("explanation"):
            lines += ["说明", str(raw["explanation"]).strip(), ""]
        if raw.get("remediation"):
            lines += ["建议", str(raw["remediation"]).strip(), ""]
        if raw.get("code_snippet"):
            lines += ["代码上下文", str(raw["code_snippet"]).strip()[:1800]]
        self._set_detail("\n".join(lines))

    def _set_detail(self, text):
        self.detail.config(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.config(state="disabled")

    def draw_gauge(self, score):
        c = self.gauge
        c.delete("all")
        cx, cy, r = 115, 112, 92
        c.create_arc(cx - r, cy - r, cx + r, cy + r, start=0, extent=180, style="arc",
                     width=16, outline="#e8e8e8")
        if score < 0:
            c.create_text(cx, cy - 26, text="—", font=FONT_BIG, fill="#bbbbbb")
            c.create_text(cx, cy - 2, text="/100", font=FONT_SMALL, fill="#bbb")
            c.create_text(cx - r + 6, cy + 8, text="0", font=("Microsoft YaHei UI", 7), fill="#ccc")
            c.create_text(cx + r - 6, cy + 8, text="100", font=("Microsoft YaHei UI", 7), fill="#ccc")
            return
        color = "#2e7d32" if score <= 20 else "#f9a825" if score <= 50 else "#e65100" if score <= 80 else "#c62828"
        if score > 0:
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=180, extent=-180 * min(score, 100) / 100,
                         style="arc", width=16, outline=color)
        c.create_text(cx, cy - 26, text=str(int(score)), font=FONT_BIG, fill=color)
        c.create_text(cx, cy - 2, text="/100", font=FONT_SMALL, fill="#888")
        c.create_text(cx - r + 6, cy + 8, text="0", font=("Microsoft YaHei UI", 7), fill="#bbb")
        c.create_text(cx + r - 6, cy + 8, text="100", font=("Microsoft YaHei UI", 7), fill="#bbb")

    # ---------- 导出 ----------
    def export_json(self):
        if not self.last_report:
            return
        p = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON 报告", "*.json")],
            initialfile="skillspector-report.json",
        )
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.last_report, f, ensure_ascii=False, indent=2)
            self.log(f"已导出：{p}")
        except OSError as e:
            messagebox.showerror("导出失败", str(e))

    def load_report_file(self, path):
        """载入一份已有 JSON 报告（离线回看）。"""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("读取报告失败", f"{path}\n\n{e}")
            return
        reports = split_reports(data)
        if not reports:
            messagebox.showerror("读取报告失败", "报告里没有 risk_assessment 字段。")
            return
        self.last_report = data
        if not self.var_target.get().strip():
            src = (reports[0].get("skill") or {}).get("source") or ""
            self.var_target.set(src or os.path.basename(path))
        self.render(reports, data, 0, None)
        self.btn_export.config(state="normal")
        self.btn_copy.config(state="normal")
        self.log(f"已载入报告：{os.path.basename(path)}")

    def copy_summary(self):
        if not self.issues:
            return
        cnt = {}
        for r in self.issues:
            cnt[r["sev"]] = cnt.get(r["sev"], 0) + 1
        head = self.var_target.get().strip()
        lines = [f"SkillSpector 体检结果：{head}",
                 "问题分布：" + " · ".join(f"{k} {v}" for k, v in cnt.items()),
                 ""]
        for r in self.issues[:60]:
            if r["sev"] in ("CRITICAL", "HIGH"):
                lines.append(f"[{r['sev']}] {r['cat']} / {r['pat']} — {r['file']}:{r['line'] or '?'}")
        if len(self.issues) > 60:
            lines.append(f"……另有 {len(self.issues) - 60} 条")
        self.root.clipboard_clear()
        self.root.clipboard_append("\n".join(lines))
        self.log("摘要已复制到剪贴板")


def enable_dpi_awareness():
    """让 Windows 别再整体放大窗口，否则 1080p 屏装不下底部。"""
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def resource_path(rel):
    """兼容源码运行与 PyInstaller 单文件打包的资源路径。"""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    try:
        root.iconbitmap(resource_path("icon.ico"))
    except Exception:  # noqa: BLE001
        pass
    app = App(root)

    argv = sys.argv[1:]
    report_path, target = None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--report", "-r") and i + 1 < len(argv):
            report_path = argv[i + 1]
            i += 2
            continue
        if not a.startswith("-") and target is None:
            target = a
        i += 1

    if report_path:
        root.after(120, lambda: app.load_report_file(report_path))
    elif target:
        app.var_target.set(target)
        root.after(350, app.start_scan)

    root.mainloop()


if __name__ == "__main__":
    main()
