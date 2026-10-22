"""
package_release.py
===================
全自動版本打包工具 (Release Packaging Suite):
  將當前專案程式碼、AI ONNX 模型檔、靜態儀表板、部署與啟動腳本打包至 releases/ 目錄下。
  預設排除 .venv, __pycache__, .git, .firebase, 101MB 備用模型大檔 (yolov8m-pose.onnx/pt)，
  保持 zip 壓縮檔精簡輕量 (~12MB)，滿足 100% 開箱即用要求。

執行方式:
  python scripts/package_release.py
"""
import os
import sys
import zipfile
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

VERSION = "v0.9.0"
DATE_STR = datetime.now().strftime("%Y%m%d")
ZIP_NAME = f"student_analytics_{VERSION}_{DATE_STR}.zip"
RELEASES_DIR = os.path.join(ROOT_DIR, "releases")
OUTPUT_ZIP_PATH = os.path.join(RELEASES_DIR, ZIP_NAME)

os.makedirs(RELEASES_DIR, exist_ok=True)

# Include directories & files
INCLUDE_DIRS = ["api", "core", "database", "dashboard", "models", "scripts", "openspec", "tests"]
INCLUDE_FILES = [
    "config.py",
    "init_db.py",
    "requirements.txt",
    ".env.example",
    "README.md",
    "VERSION.md",
    "CHANGELOG.md",
    "start.bat",
    "start.sh",
    "start_tunnel.bat"
]

# Exclusion rules
EXCLUDE_SUBSTRINGS = [
    "__pycache__",
    ".venv",
    ".git",
    ".firebase",
    "yolov8m-pose.pt",
    "yolov8m-pose.onnx",
    "releases",
    "scratch",
    ".idea",
    ".vscode"
]

print("=" * 70)
print(f"[PACKAGING] 開始打包【學生專注度與異常行為分析系統】版本: {VERSION} ({ZIP_NAME})")
print("=" * 70)

files_added = 0
total_uncompressed_bytes = 0

with zipfile.ZipFile(OUTPUT_ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zipf:
    # 1. Add individual root files
    for fn in INCLUDE_FILES:
        fp = os.path.join(ROOT_DIR, fn)
        if os.path.exists(fp):
            zipf.write(fp, fn)
            files_added += 1
            sz = os.path.getsize(fp)
            total_uncompressed_bytes += sz
            print(f"  [OK] {fn:<30} ({sz/1024:.1f} KB)")
        else:
            print(f"  [WARN] {fn}")

    # 2. Add include directories recursively
    for dir_name in INCLUDE_DIRS:
        dir_path = os.path.join(ROOT_DIR, dir_name)
        if not os.path.exists(dir_path):
            continue
            
        for root, dirs, files in os.walk(dir_path):
            # Exclude unwanted directories
            dirs[:] = [d for d in dirs if not any(ex in os.path.join(root, d) for ex in EXCLUDE_SUBSTRINGS)]
            
            for file in files:
                rel_path = os.path.relpath(os.path.join(root, file), ROOT_DIR)
                if any(ex in rel_path for ex in EXCLUDE_SUBSTRINGS):
                    continue
                    
                full_path = os.path.join(root, file)
                sz = os.path.getsize(full_path)
                zipf.write(full_path, rel_path)
                files_added += 1
                total_uncompressed_bytes += sz
                print(f"  [OK] {rel_path:<45} ({sz/1024:.1f} KB)")

zip_size_mb = os.path.getsize(OUTPUT_ZIP_PATH) / (1024 * 1024)

print("\n" + "=" * 70)
print(f"[SUCCESS] 打包完全成功")
print(f"  [OUTPUT] {OUTPUT_ZIP_PATH}")
print(f"  檔案數量: {files_added} 個檔案")
print(f"  壓縮前大小: {total_uncompressed_bytes / (1024 * 1024):.2f} MB")
print(f"  精簡壓縮檔大小: {zip_size_mb:.2f} MB")
print("=" * 70)

