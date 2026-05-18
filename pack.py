"""小工具打包核心（共用，可直接交給同事使用）。

只用 Python 標準庫，不需 pip 安裝、不寫死路徑、不依賴 launcher 或 tools.json。

命令列：
    python pack.py            # 打包目前資料夾
    python pack.py <資料夾>   # 打包指定資料夾
    python pack.py --id salary --version 1.0.2

GUI：
    python pack_gui.py        # 視窗介面（內部呼叫本檔的 build_package）

id / version 來源優先序：命令列參數 > 同資料夾 pack.json。
產出位置：本腳本所在資料夾 / {專案名稱} / {專案名稱}-v{version}.zip，
同夾另寫 release_info.txt（sha256 與 size_bytes）。
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from pathlib import Path

# 所有 zip 統一輸出到「本腳本所在資料夾」底下，再依專案名稱分子資料夾。
OUTPUT_ROOT = Path(__file__).resolve().parent

# 一律排除的建置/暫存產物（資料夾名 or glob）。新工具不用改這裡。
EXCLUDE_DIRS = {
    "build", "dist", "__pycache__", ".git", ".venv", "venv",
    "node_modules", ".idea", ".vscode", "release",
}
EXCLUDE_GLOBS = [
    "*.spec", "*.zip", "*.pyc", "*.pyo", "*.log",
    "build_log.txt", ".DS_Store", "Thumbs.db",
    ".git*", "build.bat",  # git / 編 exe 用,launcher 用不到
    "pack.json", ".packignore",  # 打包設定,launcher 不需要
    "my_tools.json", "tool_info.json", "release_info.txt",  # 打包工具的輸出/本機資料
    # 註:不排除 pack.py / pack_gui.py —— 打包工具本身要靠它們執行;
    # 一般工具資料夾不會有這兩檔,所以排不排除對它們沒差。
]

# tool_info.json 的下載網址範本（同事用自己 GitHub 帳號也適用）
URL_TEMPLATE = (
    "https://github.com/{owner}/{repo}/releases/download/"
    "v{version}/{tool_id}-v{version}.zip"
)
# 同事本機累積自己工具資料的清單（一開始不存在 = 空）
REGISTRY = OUTPUT_ROOT / "my_tools.json"

# 檔名看起來像機密 → 打包前提醒人工確認（不自動排除，由作者決定）
SENSITIVE_HINTS = [
    "*secret*", "*password*", "*credential*", "*token*", "*.key", "*.pem",
    ".env", "*.env", "settings.json", "config.json", "*employee*",
    "*.sqlite", "*.db", "id_rsa*",
]


def _gh_parts(s: str) -> list[str]:
    """把可能是 github 網址的字串拆成路徑片段（不是網址就原樣切）。"""
    s = (s or "").strip()
    s = re.sub(r"^(https?://)?(www\.)?github\.com/", "", s, flags=re.I)
    return [p for p in s.strip("/").split("/") if p]


def normalize_owner_repo(owner: str, repo: str) -> tuple[str, str]:
    """把貼成整段網址的 owner/repo 自動截成帳號 / repo 名。

    例：owner='https://github.com/burt-chen/xml-batch-convert' repo=''
        → ('burt-chen', 'xml-batch-convert')
    """
    o = (owner or "").strip()
    r = (repo or "").strip()
    op = _gh_parts(o)
    if op:
        o = op[0]
        if len(op) >= 2 and not r:  # owner 欄含 repo,且 repo 沒填 → 補上
            r = op[1]
    rp = _gh_parts(r)
    if rp:
        r = rp[-1]
    if r.endswith(".git"):
        r = r[:-4]
    return o, r


def looks_invalid(owner: str, repo: str) -> str | None:
    """回傳錯誤訊息字串；沒問題回 None。"""
    for label, v in (("GitHub 帳號", owner), ("GitHub repo", repo)):
        if not v:
            return f"「{label}」不可空白。"
        if "/" in v or " " in v or "github.com" in v.lower():
            return f"「{label}」格式不對：{v}\n只要填名稱本身,不要整段網址。"
    return None


def build_url(owner: str, repo: str, tool_id: str, version: str) -> str:
    return URL_TEMPLATE.format(
        owner=owner.strip(), repo=repo.strip(),
        tool_id=tool_id.strip(), version=version.strip(),
    )


def password_hash(pw: str) -> str:
    """解鎖密碼 → sha256（tools.json 只存雜湊，反推不出明碼）。"""
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def merge_versions(history: list | None, version: str, size_bytes: int) -> list:
    """把這次的版本併進歷史清單（同版本覆蓋 size），依語意版本排序。"""
    out = [dict(v) for v in (history or []) if v.get("version") != version]
    out.append({"version": version, "size_bytes": size_bytes})

    def key(v):
        try:
            return tuple(int(x) for x in str(v["version"]).split("."))
        except Exception:
            return (0,)

    out.sort(key=key)
    return out


def make_tool_info(meta: dict, version: str, size_bytes: int, sha256: str) -> dict:
    """依表單 meta + 打包結果，組出 tools.json 用的完整工具物件。

    meta 可含 open(bool,預設 True)、unlock_password、versions(歷史清單)。
    """
    owner, repo, tool_id = meta["owner"], meta["repo"], meta["id"]
    url = build_url(owner, repo, tool_id, version)
    homepage = (meta.get("homepage") or "").strip() \
        or f"https://github.com/{owner.strip()}/{repo.strip()}"
    history = merge_versions(meta.get("versions"), version, size_bytes)
    versions = [
        {
            "version": v["version"],
            "url": build_url(owner, repo, tool_id, v["version"]),
            "size_bytes": v.get("size_bytes", 0),
        }
        for v in history
    ]
    info = {
        "id": tool_id,
        "name": meta.get("name") or tool_id,
        "description": meta.get("description", ""),
        "version": version,
        "size_bytes": size_bytes,
        "url": url,
        "sha256": sha256,
        "category": meta.get("category", ""),
        "homepage": homepage,
        "versions": versions,
    }
    if not meta.get("open", True):
        info["hidden"] = True
        pw = (meta.get("unlock_password") or "").strip()
        if pw:
            info["unlock_hash"] = password_hash(pw)
    return info


def load_registry() -> dict:
    """讀本機工具清單（不存在或壞掉都回空）。"""
    if REGISTRY.exists():
        try:
            data = json.loads(REGISTRY.read_text(encoding="utf-8"))
            data.setdefault("tools", [])
            return data
        except Exception:
            pass
    return {"tools": []}


def save_registry(data: dict) -> None:
    REGISTRY.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def upsert_registry(entry: dict) -> dict:
    """以 id 為鍵，新增或覆蓋一筆工具資料，回傳更新後的 registry。"""
    data = load_registry()
    tools = data.setdefault("tools", [])
    for i, t in enumerate(tools):
        if t.get("id") == entry.get("id"):
            tools[i] = {**t, **entry}
            break
    else:
        tools.append(entry)
    save_registry(data)
    return data


def delete_registry(tool_id: str) -> bool:
    """從本機清單刪掉一筆工具，回傳是否真的有刪到。"""
    data = load_registry()
    tools = data.get("tools", [])
    kept = [t for t in tools if t.get("id") != tool_id]
    data["tools"] = kept
    save_registry(data)
    return len(kept) != len(tools)


def tool_info_path(tool_id: str) -> Path:
    return OUTPUT_ROOT / tool_id / "tool_info.json"


def write_tool_info(out_dir: Path, info: dict) -> Path:
    p = out_dir / "tool_info.json"
    p.write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return p


def read_tool_info(tool_id: str) -> dict | None:
    """讀該工具輸出夾既有的 tool_info.json（沒有或壞掉回 None）。"""
    p = tool_info_path(tool_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def import_tool_info(tool_id: str, src: Path) -> dict:
    """把外部給的 tool_info / tools.json 工具物件，覆蓋寫入該工具輸出夾。

    回傳解析後的 dict。會驗證格式並要求 id 相符（避免覆蓋錯工具）。
    """
    data = json.loads(Path(src).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "versions" not in data:
        raise ValueError("檔案格式不對：不是有效的工具物件（缺 versions）")
    fid = data.get("id")
    if fid and fid != tool_id:
        raise ValueError(f"檔案裡的 id 是「{fid}」，與選取的工具「{tool_id}」不符")
    out_dir = OUTPUT_ROOT / tool_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "tool_info.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return data


def read_meta(folder: Path) -> dict:
    """讀同資料夾的 pack.json（沒有就回空 dict）。"""
    f = folder / "pack.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_extra_ignores(folder: Path) -> list[str]:
    f = folder / ".packignore"
    if not f.exists():
        return []
    return [
        ln.strip()
        for ln in f.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]


def _gen_dirs(folder: Path) -> set[str]:
    """偵測「打包輸出夾」：folder 第一層中,內含 release_info.txt /
    tool_info.json / *.zip 的子資料夾,視為產出物,整夾排除。

    這讓打包工具打包自己時，不會把別的工具輸出夾掃進去。
    """
    out: set[str] = set()
    try:
        for p in folder.iterdir():
            if p.is_dir() and (
                (p / "release_info.txt").exists()
                or (p / "tool_info.json").exists()
                or any(p.glob("*.zip"))
            ):
                out.add(p.name)
    except OSError:
        pass
    return out


def _skip(rel: Path, extra: list[str], gen: set[str]) -> bool:
    if rel.parts and rel.parts[0] in gen:
        return True
    if any(part in EXCLUDE_DIRS for part in rel.parts):
        return True
    return any(fnmatch.fnmatch(rel.name, g) for g in EXCLUDE_GLOBS + extra)


def preview(folder: Path) -> dict:
    """不打包，只回傳將被納入的檔案與疑似機密清單，給 GUI 預覽用。"""
    extra = load_extra_ignores(folder)
    gen = _gen_dirs(folder)
    included: list[str] = []
    sensitive: list[str] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(folder)
        if _skip(rel, extra, gen):
            continue
        included.append(rel.as_posix())
        if any(fnmatch.fnmatch(rel.name.lower(), h) for h in SENSITIVE_HINTS):
            sensitive.append(rel.as_posix())
    return {
        "included": included,
        "sensitive": sensitive,
        "has_main_frame": (folder / "main_frame.py").exists(),
    }


def build_package(folder: Path, tool_id: str, version: str) -> dict:
    """打包成 OUTPUT_ROOT/{專案名稱}/{專案名稱}-v{version}.zip。

    回傳 zip_path / zip_name / sha256 / size_bytes / included。
    """
    import zipfile

    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise NotADirectoryError(f"找不到資料夾：{folder}")
    if not tool_id or not version:
        raise ValueError("id 與 version 不可為空")

    extra = load_extra_ignores(folder)
    gen = _gen_dirs(folder)
    out_dir = OUTPUT_ROOT / tool_id
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / f"{tool_id}-v{version}.zip"
    if zip_path.exists():
        zip_path.unlink()

    included: list[str] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(folder)
            if _skip(rel, extra, gen):
                continue
            zf.write(path, rel.as_posix())  # 扁平結構：main_frame.py 在 zip 根
            included.append(rel.as_posix())

    data = zip_path.read_bytes()
    result = {
        "zip_path": zip_path,
        "zip_name": zip_path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "included": included,
    }
    (out_dir / "release_info.txt").write_text(
        f"id:          {tool_id}\n"
        f"version:     {version}\n"
        f"zip:         {result['zip_name']}\n"
        f"size_bytes:  {result['size_bytes']}\n"
        f"sha256:      {result['sha256']}\n",
        encoding="utf-8",
    )
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="打包小工具為發佈用 zip")
    ap.add_argument("folder", nargs="?", default=".", help="工具資料夾（預設目前資料夾）")
    ap.add_argument("--id", help="工具代號（覆寫 pack.json）")
    ap.add_argument("--version", help="版本號（覆寫 pack.json）")
    args = ap.parse_args()

    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        sys.exit(f"找不到資料夾：{folder}")

    meta = read_meta(folder)
    tool_id = args.id or meta.get("id")
    version = args.version or meta.get("version")
    if not tool_id or not version:
        sys.exit(
            "缺少 id / version。請在工具資料夾放 pack.json：\n"
            '  { "id": "工具代號", "version": "1.0.0" }\n'
            "或用參數：python pack.py --id <id> --version <版本>"
        )

    pv = preview(folder)
    if not pv["has_main_frame"]:
        print("警告：資料夾內沒有 main_frame.py，launcher 可能無法載入此工具。")
    if pv["sensitive"]:
        print("⚠ 下列檔案疑似含機密，會被打包進公開 zip，請確認或加入 .packignore：")
        for f in pv["sensitive"]:
            print(f"  ! {f}")

    r = build_package(folder, tool_id, version)
    print(f"已打包 {len(r['included'])} 個檔案 → {r['zip_path']}")
    for f in r["included"]:
        print(f"  + {f}")
    print(f"\nsize_bytes:  {r['size_bytes']}\nsha256:      {r['sha256']}")
    print("\n把 size_bytes / sha256 / version 交給 catalog 維護者更新 tools.json，"
          "並把 zip 上傳到該工具的 GitHub Release。")


if __name__ == "__main__":
    main()
