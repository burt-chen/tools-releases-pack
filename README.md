# 小工具打包工具 (tools-releases-pack)

把小工具資料夾打包成 MyTools Launcher 用的發佈 zip，並產生 catalog
（`tools.json`）需要的工具物件 `tool_info.json`。

只用 Python 標準庫（含 tkinter），免安裝任何套件。同事拿到
`pack.py` + `pack_gui.py` + `main_frame.py` 三支即可用，全程不需 GitHub 權限、
不碰 `tools.json`。

## 功能

兩個頁簽：

1. **小工具資料** — 本機工具清單，可新增 / 編輯 / 刪除（存 `my_tools.json`，
   一開始空的）。每筆含 id、名稱、描述、分類、GitHub 帳號 / repo、預設資料夾、
   是否開放、解鎖密碼。也能「匯入 tool_info」把外部給的權威資料覆蓋進來。
2. **打包** — 從清單挑工具 → 填版本 → 列出將打包的檔案（疑似機密會紅字警告）
   → 產生 zip + `tool_info.json`。

## 結構

```
tools-releases-pack/
├── pack.py        # 核心：掃檔/排除/機密偵測/壓 zip/算 sha256/組 tool_info/本機清單
├── pack_gui.py    # 兩頁簽 GUI（PackApp）
├── main_frame.py  # 供 MyTools Launcher 嵌入的入口（create_frame）
└── my_tools.json  # 本機工具清單（自動產生,已列入 .gitignore,不進版控）
```

## 執行方式

**獨立執行**：

```powershell
python pack_gui.py
# 或命令列：python pack.py <資料夾> --id <id> --version <版本>
```

**透過 MyTools Launcher**：安裝後直接開啟（本工具設為隱藏，需解鎖碼才看得到）。

需要 Python 3.8+（內建 tkinter）。

## 產出位置

zip 與 `tool_info.json` 統一放在**本工具所在資料夾**底下，依工具代號分子夾：

```
tools-releases-pack/<工具id>/
├── <工具id>-v<版本>.zip
├── tool_info.json      # 給 catalog 維護者更新 tools.json 用的完整工具物件
└── release_info.txt    # sha256 / size_bytes
```

## 打包規則

- **一律排除**：`build/` `dist/` `__pycache__/` `.git*` `*.spec` `build.bat`
  `*.zip` `tests/` 等建置/暫存產物。
- 工具資料夾可放選用的 `.packignore`（每行一個 glob）排除自己的機密 / 多餘檔。
- 檔名疑似機密（`*password*`、`settings.json`、`*.key`、`*employee*`…）會在
  打包前紅字警告並要求確認，避免把密碼 / 個資壓進公開 zip。
- zip 為扁平結構，`main_frame.py` 在根目錄（launcher 解壓後直接載入）。

## 版本歷史（回滾用）

`tool_info.json` 的 `versions[]` 會累積打包過的所有版本（供 launcher 切換 /
回滾），top-level `version`/`url`/`size` 為這次打的最新版。

**版本歷史以既有 `tool_info.json` 為準**：打包前先讀該工具輸出夾的
`tool_info.json`，用它的版本清單當基底；本機清單 `my_tools.json` 只是後備。
所以 catalog 維護者可把 `tools.json` 裡該工具的物件給作者，作者用
「匯入 tool_info」覆蓋進來，之後打包就接續正確的歷史，不怕本機清單被改壞。

## 開放 / 隱藏

- 開放：不寫 `hidden`，launcher 所有人可見。
- 不開放：`tool_info.json` 寫 `"hidden": true` + `"unlock_hash"`（解鎖密碼的
  sha256，反推不出明碼）。launcher 需輸入解鎖碼才看得到。

## ⚠️ 安全注意

- `my_tools.json` 是各人本機資料，**可能含解鎖密碼明碼**，已列入 `.gitignore`，
  **絕不可外流**。給同事只給 `pack.py` + `pack_gui.py` + `main_frame.py` 三支。
- 工具 zip 會放公開 GitHub Release，打包前務必看過檔案清單，機密檔加進
  `.packignore`。

## 交付流程（作者 → catalog 維護者）

1. 作者打包 → 得到 `<id>/` 下的 zip + `tool_info.json`
2. 作者在**自己 GitHub 帳號**的 repo 發 Release 上傳該 zip
3. 把 `tool_info.json`（或其中的 version / size_bytes / sha256 / url）交給
   catalog 維護者
4. 維護者據此更新 `小工具管理/tools.json` 並 push `tools-launcher` repo
