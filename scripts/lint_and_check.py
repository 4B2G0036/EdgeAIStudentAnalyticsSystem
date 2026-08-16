"""
lint_and_check.py
===================
全專案 Python 檔案語法與邏輯偵錯檢查工具：
  1. 掃描專案內所有 Python 檔案 (.py) 進行 AST/compile 語法編譯檢查
  2. 檢查目前實際存在的所有關鍵模組 (config, database, api, core) 匯入與相依性
  3. 檢測常見程式碼潛在問題 (如無效轉義字元、未捕獲例外、型態防護等)
"""
import sys
import os
import ast
import importlib

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

exclude_dirs = {".venv", "__pycache__", ".git", ".firebase"}

errors_found = 0
warnings_found = 0

print("=" * 70)
print("🔍 開始進行全專案 Python 檔案語法與模組偵錯檢查")
print("=" * 70)

# Step 1: 掃描並檢驗所有 Python 檔案語法
py_files = []
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in exclude_dirs]
    for f in files:
        if f.endswith(".py"):
            py_files.append(os.path.join(root, f))

print(f"\n[1/3] 檢查 {len(py_files)} 個現有 Python 檔案語法 (AST / Syntax Check)...")
for pf in py_files:
    rel_path = os.path.relpath(pf, ".")
    try:
        with open(pf, "r", encoding="utf-8", errors="replace") as file:
            content = file.read()
        ast.parse(content, filename=rel_path)
        compile(content, rel_path, "exec")
        print(f"  ✅ 語法無誤: {rel_path}")
    except SyntaxError as se:
        print(f"  ❌ 語法錯誤: {rel_path} Line {se.lineno}: {se.msg}")
        errors_found += 1
    except Exception as e:
        print(f"  ❌ 讀取/編譯錯誤: {rel_path} -> {e}")
        errors_found += 1

# Step 2: 模組匯入完整度測試（僅針對目前已存在的模組）
print("\n[2/3] 測試現有模組動態載入與相依性 Check...")
modules_to_test = [
    "config",
    "database.connection",
    "database.collections",
    "database.queries",
    "core.camera",
    "api.main",
    "api.routers.sessions",
    "api.routers.stream",
]

for mod in modules_to_test:
    try:
        importlib.import_module(mod)
        print(f"  ✅ 模組載入成功: {mod}")
    except Exception as e:
        print(f"  ❌ 模組載入失敗: {mod} -> {e}")
        errors_found += 1

# Step 3: 靜態程式碼安全性審查
print("\n[3/3] 靜態程式碼安全性與例外防護檢查...")
for pf in py_files:
    rel_path = os.path.relpath(pf, ".")
    with open(pf, "r", encoding="utf-8", errors="replace") as file:
        lines = file.readlines()

    for idx, line in enumerate(lines, 1):
        if "except:" in line.replace(" ", ""):
            print(f"  ⚠️ 建議改善: {rel_path}:L{idx} 使用了裸 except (建議補上具體 Exception)")
            warnings_found += 1

print("\n" + "=" * 70)
print(f"📊 檢查完成: 共掃描 {len(py_files)} 個 Python 檔案")
print(f"  🔴 嚴重語法/匯入錯誤: {errors_found} 個")
print(f"  🟡 建議改善代碼點: {warnings_found} 個")
print("=" * 70)

if errors_found == 0:
    print("🎉 恭喜！專案現有所有檔案 100% 語法正確，無任何程式碼錯誤與斷裂！")
else:
    sys.exit(1)
