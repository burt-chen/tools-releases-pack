"""小工具打包 — 視窗介面（兩個頁簽）。

只用標準庫（tkinter），免安裝：
    python pack_gui.py

頁簽 1「小工具資料」：本機工具清單，可新增 / 編輯 / 刪除（存 my_tools.json，
                      一開始空的）。
頁簽 2「打包」：從清單挑工具 → 填版本 → 產生 zip + tool_info.json。

完全不碰 tools.json，也不需要任何 GitHub 權限。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pack


# ── 新增 / 編輯 工具資料的對話框 ──────────────────────────────

class ToolDialog(tk.Toplevel):
    FIELDS = [
        ("id", "工具代號 (id)", "zip 檔名與安裝資料夾名,英數與 - _"),
        ("name", "顯示名稱", "launcher 上顯示的名稱"),
        ("description", "描述", ""),
        ("category", "分類", "例:資料處理 / 辦公自動化"),
        ("owner", "GitHub 帳號", "你自己的帳號,用來組下載網址"),
        ("repo", "GitHub repo", "你放這工具的 repo 名"),
    ]

    def __init__(self, parent, existing: dict | None = None):
        super().__init__(parent)
        self.title("編輯工具" if existing else "新增工具")
        self.resizable(False, False)
        self.transient(parent)
        self.result: dict | None = None
        self._is_edit = existing is not None

        self.vars = {k: tk.StringVar(value=(existing or {}).get(k, ""))
                     for k, _, _ in self.FIELDS}
        self.folder = tk.StringVar(value=(existing or {}).get("folder", ""))
        self.open_var = tk.BooleanVar(value=(existing or {}).get("open", True))
        self.pw = tk.StringVar(value=(existing or {}).get("unlock_password", ""))

        frm = ttk.Frame(self, padding=14)
        frm.grid(sticky="nsew")
        frm.columnconfigure(1, weight=1)
        r = 0
        for key, label, hint in self.FIELDS:
            ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
            e = ttk.Entry(frm, textvariable=self.vars[key], width=46)
            e.grid(row=r, column=1, sticky="ew", padx=6, pady=4)
            if key == "id" and self._is_edit:
                e.configure(state="disabled")  # id 是鍵,編輯時不可改
            if hint:
                ttk.Label(frm, text=hint, foreground="#888").grid(
                    row=r + 1, column=1, sticky="w", padx=6)
                r += 1
            r += 1

        ttk.Label(frm, text="預設資料夾").grid(row=r, column=0, sticky="w", padx=6, pady=4)
        fr = ttk.Frame(frm)
        fr.grid(row=r, column=1, sticky="ew", padx=6, pady=4)
        fr.columnconfigure(0, weight=1)
        ttk.Entry(fr, textvariable=self.folder).grid(row=0, column=0, sticky="ew")
        ttk.Button(fr, text="瀏覽…", command=self._pick).grid(row=0, column=1, padx=(6, 0))
        r += 1

        ttk.Label(frm, text="是否開放").grid(row=r, column=0, sticky="w", padx=6, pady=4)
        ttk.Checkbutton(frm, text="開放工具（所有人可見,不需密碼）",
                        variable=self.open_var,
                        command=self._toggle_pw).grid(
            row=r, column=1, sticky="w", padx=6, pady=4)
        r += 1
        ttk.Label(frm, text="解鎖密碼").grid(row=r, column=0, sticky="w", padx=6, pady=4)
        self._pw_entry = ttk.Entry(frm, textvariable=self.pw, width=46, show="•")
        self._pw_entry.grid(row=r, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(frm, text="不開放時必填;launcher 需輸入此密碼才看得到此工具",
                  foreground="#888").grid(row=r + 1, column=1, sticky="w", padx=6)
        r += 2
        self._toggle_pw()

        bar = ttk.Frame(frm)
        bar.grid(row=r, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(bar, text="取消", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(bar, text="確定", command=self._ok).pack(side="right", padx=4)

        self.grab_set()
        self.wait_window(self)

    def _toggle_pw(self):
        self._pw_entry.configure(
            state="disabled" if self.open_var.get() else "normal")

    def _pick(self):
        d = filedialog.askdirectory(title="選擇此工具的資料夾", parent=self)
        if d:
            self.folder.set(d)
            if not self.vars["id"].get().strip():
                self.vars["id"].set(Path(d).name)
            if not self.vars["name"].get().strip():
                self.vars["name"].set(Path(d).name)

    def _ok(self):
        tid = self.vars["id"].get().strip()
        if not tid:
            messagebox.showwarning("缺少資訊", "「工具代號 (id)」必填。", parent=self)
            return
        # owner/repo:貼整段 github 網址會自動截成帳號 / repo 名
        owner, repo = pack.normalize_owner_repo(
            self.vars["owner"].get(), self.vars["repo"].get())
        self.vars["owner"].set(owner)   # 把修正後的值回填,讓使用者看到
        self.vars["repo"].set(repo)
        err = pack.looks_invalid(owner, repo)
        if err:
            messagebox.showwarning("GitHub 帳號 / repo 有誤", err, parent=self)
            return
        is_open = bool(self.open_var.get())
        pw = self.pw.get().strip()
        if not is_open and not pw:
            messagebox.showwarning(
                "缺少資訊", "不開放的工具必須設定解鎖密碼。", parent=self)
            return
        self.result = {k: self.vars[k].get().strip() for k, _, _ in self.FIELDS}
        self.result["owner"] = owner
        self.result["repo"] = repo
        self.result["name"] = self.result["name"] or tid
        self.result["folder"] = self.folder.get().strip()
        self.result["open"] = is_open
        self.result["unlock_password"] = "" if is_open else pw
        self.destroy()


# ── 主視窗 ──────────────────────────────────────────────────

class PackApp:
    def __init__(self, parent: tk.Widget):
        # parent 可以是 tk.Tk（獨立執行）或 launcher 給的 Frame（嵌入執行）。
        # 一律把 UI 建進自己的 self.frame，window 標題/大小由 main() 設。
        self.parent = parent
        self.root = parent          # 給 Toplevel / messagebox 當 parent 用
        self.frame = ttk.Frame(parent)

        nb = ttk.Notebook(self.frame)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_data = ttk.Frame(nb)
        self.tab_pack = ttk.Frame(nb)
        nb.add(self.tab_data, text="  小工具資料  ")
        nb.add(self.tab_pack, text="  打包  ")

        self._build_data_tab()
        self._build_pack_tab()
        self._reload()

    # ---- 頁簽 1：小工具資料 ----

    def _build_data_tab(self):
        f = self.tab_data
        f.rowconfigure(0, weight=1)
        f.columnconfigure(0, weight=1)

        cols = ("id", "name", "category", "open", "gh", "folder")
        titles = {"id": "代號", "name": "名稱", "category": "分類",
                  "open": "開放", "gh": "GitHub", "folder": "資料夾"}
        widths = {"id": 110, "name": 140, "category": 80, "open": 48,
                  "gh": 170, "folder": 190}
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=titles[c])
            self.tree.column(c, width=widths[c], anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        sb = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=10)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", lambda _e: self._edit_tool())

        bar = ttk.Frame(f)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(bar, text="新增", command=self._add_tool).pack(side="left")
        ttk.Button(bar, text="編輯", command=self._edit_tool).pack(side="left", padx=6)
        ttk.Button(bar, text="刪除", command=self._del_tool).pack(side="left")
        ttk.Button(bar, text="匯出資料",
                   command=self._export_data).pack(side="left", padx=(16, 0))
        ttk.Button(bar, text="匯入資料",
                   command=self._import_data).pack(side="left", padx=6)
        ttk.Button(bar, text="匯入 tool_info",
                   command=self._import_info).pack(side="right")

    def _selected_id(self) -> str | None:
        sel = self.tree.selection()
        return self.tree.item(sel[0], "values")[0] if sel else None

    def _add_tool(self):
        dlg = ToolDialog(self.root)
        if dlg.result:
            entry = dict(dlg.result)
            entry["last_version"] = "1.0.0"
            pack.upsert_registry(entry)
            self._reload(select_id=entry["id"])

    def _edit_tool(self):
        tid = self._selected_id()
        if not tid:
            messagebox.showinfo("請先選取", "請先在清單中選一個工具。")
            return
        cur = next((t for t in self._reg["tools"] if t.get("id") == tid), None)
        dlg = ToolDialog(self.root, existing=cur)
        if dlg.result:
            merged = {**cur, **dlg.result}
            pack.upsert_registry(merged)
            self._reload(select_id=tid)

    def _del_tool(self):
        tid = self._selected_id()
        if not tid:
            messagebox.showinfo("請先選取", "請先在清單中選一個工具。")
            return
        if messagebox.askyesno("刪除", f"確定從本機清單刪除「{tid}」?\n"
                                       "(只刪清單記錄,不會動到任何檔案或已產生的 zip)"):
            pack.delete_registry(tid)
            self._reload()

    def _import_info(self):
        tid = self._selected_id()
        if not tid:
            messagebox.showinfo("請先選取", "請先選一個工具,再匯入它的 tool_info.json。")
            return
        src = filedialog.askopenfilename(
            title=f"選擇要匯入給「{tid}」的 tool_info.json",
            filetypes=[("tool_info / JSON", "*.json"), ("所有檔案", "*.*")])
        if not src:
            return
        try:
            data = pack.import_tool_info(tid, Path(src))
        except Exception as e:
            messagebox.showerror("匯入失敗", str(e))
            return
        # 版本歷史以匯入檔為準,同步進本機清單
        cur = next((t for t in self._reg["tools"] if t.get("id") == tid), {})
        vers = [{"version": v.get("version"),
                 "size_bytes": v.get("size_bytes", 0)}
                for v in data.get("versions", [])]
        pack.upsert_registry({
            **cur,
            "versions": vers,
            "last_version": data.get("version", cur.get("last_version", "")),
        })
        self._reload(select_id=tid)
        vlist = ", ".join(v["version"] for v in vers) or "(無)"
        messagebox.showinfo(
            "匯入完成",
            f"已覆蓋「{tid}」的 tool_info.json,版本歷史以此檔為準。\n\n"
            f"版本:{vlist}\n\n"
            "之後打包會接續這份歷史往上加新版本。")

    def _export_data(self):
        dest = filedialog.asksaveasfilename(
            title="匯出小工具資料", defaultextension=".json",
            initialfile="my_tools_backup.json",
            filetypes=[("JSON", "*.json")])
        if not dest:
            return
        try:
            n = pack.export_registry(Path(dest))
        except Exception as e:
            messagebox.showerror("匯出失敗", str(e))
            return
        messagebox.showwarning(
            "匯出完成",
            f"已匯出 {n} 個工具到:\n{dest}\n\n"
            "⚠ 此檔含工具設定,隱藏工具的解鎖密碼為明碼,"
            "請妥善保管、勿外流。")

    def _import_data(self):
        src = filedialog.askopenfilename(
            title="匯入小工具資料",
            filetypes=[("JSON", "*.json"), ("所有檔案", "*.*")])
        if not src:
            return
        replace = messagebox.askyesno(
            "匯入方式",
            "要「整份覆蓋」目前的小工具資料嗎?\n\n"
            "是 = 整份取代(現有清單會被清掉換成檔案內容)\n"
            "否 = 合併(同 id 覆蓋、新 id 新增,其餘保留)")
        try:
            r = pack.import_registry(Path(src), replace=replace)
        except Exception as e:
            messagebox.showerror("匯入失敗", str(e))
            return
        self._reload()
        messagebox.showinfo(
            "匯入完成",
            f"新增 {r['added']} 筆、更新 {r['updated']} 筆,"
            f"目前共 {r['total']} 筆。")

    # ---- 頁簽 2：打包 ----

    def _build_pack_tab(self):
        f = self.tab_pack
        f.columnconfigure(1, weight=1)
        self.sel = tk.StringVar()
        self.folder = tk.StringVar()
        self.version = tk.StringVar(value="1.0.0")
        self.zipname = tk.StringVar(value="—")
        self.url = tk.StringVar(value="—")
        self.last_zip: Path | None = None
        for v in (self.version,):
            v.trace_add("write", lambda *_: self._refresh_derived())

        pad = {"padx": 8, "pady": 5}
        r = 0
        ttk.Label(f, text="工具").grid(row=r, column=0, sticky="w", **pad)
        self.combo = ttk.Combobox(f, textvariable=self.sel, state="readonly")
        self.combo.grid(row=r, column=1, columnspan=2, sticky="ew", **pad)
        self.combo.bind("<<ComboboxSelected>>", lambda _e: self._on_select())
        r += 1

        ttk.Label(f, text="要打包的資料夾").grid(row=r, column=0, sticky="w", **pad)
        ttk.Entry(f, textvariable=self.folder).grid(row=r, column=1, sticky="ew", **pad)
        ttk.Button(f, text="瀏覽…", command=self._pick).grid(row=r, column=2, **pad)
        r += 1

        ttk.Label(f, text="版本").grid(row=r, column=0, sticky="w", **pad)
        ttk.Entry(f, textvariable=self.version).grid(row=r, column=1, columnspan=2, sticky="ew", **pad)
        r += 1

        ttk.Label(f, text="壓縮檔名").grid(row=r, column=0, sticky="w", **pad)
        ttk.Label(f, textvariable=self.zipname, font=("Consolas", 11, "bold"),
                  foreground="#1a6f1a").grid(row=r, column=1, columnspan=2, sticky="w", **pad)
        r += 1
        ttk.Label(f, text="下載網址").grid(row=r, column=0, sticky="w", **pad)
        ttk.Label(f, textvariable=self.url, foreground="#555",
                  wraplength=520, justify="left").grid(
            row=r, column=1, columnspan=2, sticky="w", **pad)
        r += 1

        ttk.Separator(f).grid(row=r, column=0, columnspan=3, sticky="ew", pady=4)
        r += 1
        ttk.Label(f, text="將打包的檔案（請確認沒有密碼或個資）").grid(
            row=r, column=0, columnspan=3, sticky="w", **pad)
        r += 1
        self.txt = tk.Text(f, height=9, wrap="none")
        self.txt.grid(row=r, column=0, columnspan=3, sticky="nsew", padx=8)
        self.txt.tag_config("warn", foreground="#c0392b")
        self.txt.tag_config("muted", foreground="#888")
        self.txt.configure(state="disabled")
        f.rowconfigure(r, weight=1)
        r += 1

        bar = ttk.Frame(f)
        bar.grid(row=r, column=0, columnspan=3, sticky="ew", pady=10, padx=8)
        ttk.Button(bar, text="重新整理清單", command=self._preview).pack(side="left")
        ttk.Button(bar, text="打包並產生 tool_info", command=self._pack).pack(side="right")
        self.btn_open = ttk.Button(bar, text="開啟輸出資料夾", command=self._open_out,
                                   state="disabled")
        self.btn_open.pack(side="right", padx=8)

    # ---- 共用：重新載入清單 ----

    def _reload(self, select_id: str | None = None):
        self._reg = pack.load_registry()
        tools = self._reg.get("tools", [])

        for i in self.tree.get_children():
            self.tree.delete(i)
        for t in tools:
            gh = f'{t.get("owner", "")}/{t.get("repo", "")}'.strip("/")
            opn = "是" if t.get("open", True) else "🔒否"
            self.tree.insert("", "end", values=(
                t.get("id", ""), t.get("name", ""), t.get("category", ""),
                opn, gh, t.get("folder", "")))
            if t.get("id") == select_id:
                last = self.tree.get_children()[-1]
                self.tree.selection_set(last)
                self.tree.see(last)

        self._by_label = {}
        labels = []
        for t in tools:
            lbl = f'{t.get("name") or t.get("id")}  ({t.get("id")})'
            self._by_label[lbl] = t
            labels.append(lbl)
        self.combo["values"] = labels
        if select_id:
            for lbl, t in self._by_label.items():
                if t.get("id") == select_id:
                    self.sel.set(lbl)
                    break
        elif labels and self.sel.get() not in labels:
            self.sel.set("")
        self._on_select()

    # ---- 打包頁行為 ----

    def _on_select(self):
        t = self._by_label.get(self.sel.get())
        if not t:
            self.folder.set("")
            self.version.set("1.0.0")
            self._preview()
            return
        self.folder.set(t.get("folder", ""))
        self.version.set(t.get("last_version", "") or "1.0.0")
        self._refresh_derived()
        self._preview()

    def _pick(self):
        d = filedialog.askdirectory(title="選擇要打包的工具資料夾")
        if d:
            self.folder.set(d)
            self._preview()

    def _refresh_derived(self):
        t = self._by_label.get(self.sel.get())
        ver = self.version.get().strip()
        tid = (t or {}).get("id", "")
        self.zipname.set(f"{tid}-v{ver}.zip" if tid and ver else "—")
        if t and ver and t.get("owner") and t.get("repo"):
            self.url.set(pack.build_url(t["owner"], t["repo"], tid, ver))
        else:
            self.url.set("（在「小工具資料」填好 帳號/repo 後自動產生）")

    def _set_text(self, lines):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        for s, tag in lines:
            self.txt.insert("end", s + "\n", tag)
        self.txt.configure(state="disabled")

    def _preview(self):
        folder = self.folder.get().strip()
        if not folder or not Path(folder).is_dir():
            self._set_text([("選好工具與資料夾後,這裡會列出將打包的檔案。", "muted")])
            return
        pv = pack.preview(Path(folder))
        lines = []
        if not pv["has_main_frame"]:
            lines.append(("⚠ 沒有 main_frame.py，launcher 可能無法載入此工具。", "warn"))
        if pv["sensitive"]:
            lines.append(("⚠ 下列檔案疑似含機密，會進公開 zip！確認或加進 .packignore：", "warn"))
            lines += [(f"   ! {x}", "warn") for x in pv["sensitive"]]
            lines.append(("", "muted"))
        lines += [(f"  + {x}", "") for x in pv["included"]]
        lines.append((f"\n共 {len(pv['included'])} 個檔案", "muted"))
        self._set_text(lines)

    def _pack(self):
        t = self._by_label.get(self.sel.get())
        if not t:
            messagebox.showwarning(
                "沒有可打包的工具",
                "請先到「小工具資料」頁簽新增一個工具,再回來打包。")
            return
        folder = self.folder.get().strip()
        ver = self.version.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning("缺少資料夾", "請選擇要打包的資料夾。")
            return
        if not ver:
            messagebox.showwarning("缺少版本", "請填版本。")
            return

        pv = pack.preview(Path(folder))
        if pv["sensitive"] and not messagebox.askyesno(
            "疑似機密檔案",
            "下列檔案會被打包進公開 zip：\n\n  "
            + "\n  ".join(pv["sensitive"])
            + "\n\n確定它們不含密碼 / 個資,要繼續嗎？",
            icon="warning", default="no",
        ):
            return

        try:
            r = pack.build_package(Path(folder), t["id"], ver)
            # 版本歷史以既有 tool_info.json 為準（同事本機清單可能改壞），
            # 沒有才退回用本機 my_tools.json 的紀錄。
            existing = pack.read_tool_info(t["id"])
            base_versions = (existing or {}).get("versions") \
                or t.get("versions")
            new_versions = pack.merge_versions(
                base_versions, ver, r["size_bytes"])
            meta2 = {**t, "folder": folder, "last_version": ver,
                     "versions": new_versions}
            info = pack.make_tool_info(meta2, ver, r["size_bytes"], r["sha256"])
            info_path = pack.write_tool_info(r["zip_path"].parent, info)
        except Exception as e:
            messagebox.showerror("打包失敗", str(e))
            return

        # 記住這次用的資料夾、版本與版本歷史(回滾用)
        pack.upsert_registry(meta2)
        self._reload(select_id=t["id"])
        self.last_zip = r["zip_path"]
        self.btn_open.configure(state="normal")
        self._set_text([
            (f"✓ 已產生 {r['zip_name']}（{len(r['included'])} 個檔案）", ""),
            (f"   zip:        {r['zip_path']}", "muted"),
            (f"   tool_info:  {info_path}", "muted"),
            ("", "muted"),
            (f"size_bytes:  {r['size_bytes']}", ""),
            (f"sha256:      {r['sha256']}", ""),
            (f"url:         {info['url']}", ""),
            (f"版本歷史:    {', '.join(v['version'] for v in info['versions'])}"
             + ("   🔒 隱藏工具(需解鎖密碼)" if info.get("hidden") else ""), ""),
            ("", "muted"),
            ("把這個資料夾裡的 zip + tool_info.json 交給 catalog 維護者,", "muted"),
            ("由他更新 tools.json。你不需要碰 tools.json 或 GitHub 權限。", "muted"),
        ])
        messagebox.showinfo(
            "完成",
            f"已產生：\n{r['zip_path']}\n{info_path}\n\n"
            "把這兩個檔交給 catalog 維護者即可。")

    def _open_out(self):
        if not self.last_zip:
            return
        out = self.last_zip.parent
        try:
            if sys.platform == "win32":
                os.startfile(out)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.run(["open", out])
            else:
                subprocess.run(["xdg-open", out])
        except Exception as e:
            messagebox.showerror("無法開啟", str(e))


def create_frame(parent: tk.Widget) -> ttk.Frame:
    """供 MyTools Launcher 嵌入用：回傳建好 UI 的 Frame。"""
    return PackApp(parent).frame


def main():
    root = tk.Tk()
    root.title("小工具打包")
    root.geometry("760x620")
    root.minsize(680, 560)
    app = PackApp(root)
    app.frame.pack(fill="both", expand=True)
    root.mainloop()


if __name__ == "__main__":
    main()
