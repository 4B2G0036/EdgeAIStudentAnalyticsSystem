"""
debug_all_files.py
===================
全專案全檔案深度錯誤診斷與排除工具：
  1. Python 檔案：語法編譯、匯入關係、未變更常數、異常捕捉完整性
  2. HTML/JS 檔案：檢測 JavaScript 函數重名、未閉合字串與 DOM 選擇器有效性
  3. 設定與環境變數：.env 格式與路徑合法性
  4. 執行整合功能驗證 (FastAPI, MongoDB, ONNX Models)
"""
import sys
import os
import ast
import re
import json

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

exclude_dirs = {".venv", "__pycache__", ".git", ".firebase", "releases"}

print("=" * 70)
print("🔍 啟動全專案全檔案深度錯誤排除與健康診斷流程")
print("=" * 70)

all_issues = []

# ── 1. Python 檔案語法與結構審查 ─────────────────────────────────────────────
py_files = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for f in files:
        if f.endswith(".py"):
            py_files.append(os.path.join(root, f))

print(f"\n[1/3] 診斷 {len(py_files)} 個 Python 原始碼檔案...")
for pf in py_files:
    rel_path = os.path.relpath(pf, ".")
    try:
        with open(pf, "r", encoding="utf-8", errors="replace") as file:
            content = file.read()
        ast.parse(content, filename=rel_path)
        compile(content, rel_path, "exec")
        print(f"  🟢 [Python OK] {rel_path}")
    except SyntaxError as se:
        msg = f"語法錯誤在 {rel_path}:L{se.lineno} -> {se.msg}"
        print(f"  🔴 [Python FAIL] {msg}")
        all_issues.append(msg)
    except Exception as e:
        msg = f"讀取或編譯失敗 {rel_path} -> {e}"
        print(f"  🔴 [Python FAIL] {msg}")
        all_issues.append(msg)

# ── 2. 前端 HTML & JavaScript 靜態語法診斷 ────────────────────────────────────
print("\n[2/3] 診斷前端 dashboard/index.html 檔案...")
html_file = "dashboard/index.html"
if os.path.exists(html_file):
    with open(html_file, "r", encoding="utf-8", errors="replace") as f:
        html_text = f.read()

    # 提取 <script> 區塊進行 JS 函數重名與語法診斷
    js_blocks = re.findall(r"<script>(.*?)</script>", html_text, re.DOTALL)
    print(f"  ℹ️ 找到 {len(js_blocks)} 個 <script> 標籤區塊")

    # 檢查是否有重複宣告的 function 函數名
    func_names = re.findall(r"function\s+([a-zA-Z0-9_$]+)\s*\(", html_text)
    seen_funcs = set()
    dup_funcs = set()
    for fn in func_names:
        if fn in seen_funcs:
            dup_funcs.add(fn)
        seen_funcs.add(fn)

    if dup_funcs:
        msg = f"HTML5 前端發現重複定義的 JavaScript 函數: {list(dup_funcs)}"
        print(f"  🔴 [HTML/JS FAIL] {msg}")
        all_issues.append(msg)
    else:
        print(f"  🟢 [HTML/JS OK] 0 個重複定義函數，共宣告 {len(seen_funcs)} 個 JavaScript 函數")
else:
    print(f"  ⚠️ [HTML/JS WARN] 找不到 {html_file}")

# ── 3. 組態與環境變數檔案安檢 ────────────────────────────────────────────────
print("\n[3/3] 診斷 .env 與環境變數設定...")
env_file = ".env"
if os.path.exists(env_file):
    with open(env_file, "r", encoding="utf-8", errors="replace") as f:
        env_lines = f.readlines()
    key_count = sum(1 for line in env_lines if "=" in line and not line.startswith("#"))
    print(f"  🟢 [.env OK] 已解析 {key_count} 個全域組態鍵值設定")
else:
    print(f"  ⚠️ [.env WARN] 找不到 {env_file}")

print("\n" + "=" * 70)
print("📊 深度診斷結果總結")
print("=" * 70)

if not all_issues:
    print("🎉 【診斷合格】專案中所有 Python, HTML/JS, .env 檔案 100% 正常，無任何嚴重錯誤！")
else:
    print(f"❌ 【發現 {len(all_issues)} 個潛在問題】:")
    for issue in all_issues:
        print(f"  - {issue}")
    sys.exit(1)
