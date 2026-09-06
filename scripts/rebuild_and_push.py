"""
rebuild_and_push.py
===================
依版本 (v0.1.0 ~ v0.8.0) 重建乾淨的 Git 歷史 Commit，
建立 annotated tag，並推送到 GitHub 遠端倉庫：
https://github.com/4B2G0036/EdgeAIStudentAnalyticsSystem
"""

import os
import sys
import shutil
import zipfile
import subprocess
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIT_EXE = r"C:\Program Files\Git\bin\git.exe"
RELEASES_DIR = os.path.join(ROOT_DIR, "releases")
BUILD_DIR = os.path.join(ROOT_DIR, "scratch", "git_build")
REMOTE_CLEAN_URL = "https://github.com/4B2G0036/EdgeAIStudentAnalyticsSystem.git"

VERSIONS = [
    {
        "tag": "v0.1.0",
        "zip": "student_analytics_v0.1.0_20260816.zip",
        "date": "2026-08-16T14:00:00+08:00",
        "message": "feat: v0.1.0 - 專案初始化與基礎架構 (FastAPI 基礎路由、MongoDB 連線、config.py 全域設定)"
    },
    {
        "tag": "v0.1.1",
        "zip": "student_analytics_v0.1.1_20260816.zip",
        "date": "2026-08-16T15:10:00+08:00",
        "message": "feat: v0.1.1 - 歷史課程列表與搜尋分頁、下課確定對話框 (Modal)、報表介面"
    },
    {
        "tag": "v0.2.0",
        "zip": "student_analytics_v0.2.0_20260816.zip",
        "date": "2026-08-16T16:30:00+08:00",
        "message": "feat: v0.2.0 - 前端互動式 API 網址設定 (promptApiUrl) 與即時指標輪詢"
    },
    {
        "tag": "v0.2.1",
        "zip": "student_analytics_v0.2.1_20260816.zip",
        "date": "2026-08-16T17:23:00+08:00",
        "message": "feat: v0.2.1 - 本機 WebCam HTML5 getUserMedia 直連、雙鏡頭模式切換、隱私遮罩"
    },
    {
        "tag": "v0.3.0",
        "zip": "student_analytics_v0.3.0_20260816.zip",
        "date": "2026-08-16T17:30:00+08:00",
        "message": "feat: v0.3.0 - 前端儀表板 UI 優化與即時監控圖表整合"
    },
    {
        "tag": "v0.4.0",
        "zip": "student_analytics_v0.4.0_20260816.zip",
        "date": "2026-08-16T17:40:00+08:00",
        "message": "feat: v0.4.0 - 課堂學生專注度分析引擎初步整合與異常事件偵測"
    },
    {
        "tag": "v0.4.1",
        "zip": "student_analytics_v0.4.1_20260816.zip",
        "date": "2026-08-16T17:45:00+08:00",
        "message": "feat: v0.4.1 - 專注度評分算法微調與異常事件告警防抖"
    },
    {
        "tag": "v0.5.0",
        "zip": "student_analytics_v0.5.0_20260816.zip",
        "date": "2026-08-16T17:51:00+08:00",
        "message": "feat: v0.5.0 - MongoDB 8.3.7 整合、YOLOv8-Pose ONNX 匯出與推論驗證 (21ms/103ms)"
    },
    {
        "tag": "v0.6.0",
        "zip": "student_analytics_v0.6.0_20260816.zip",
        "date": "2026-08-16T20:18:00+08:00",
        "message": "feat: v0.6.0 - 全系統整合驗證、CORS 修復、Cloudflare HTTPS 穿透、core/ 8 大視覺 AI 模組"
    },
    {
        "tag": "v0.7.0",
        "zip": "student_analytics_v0.7.0_20260906.zip",
        "date": "2026-09-06T22:56:00+08:00",
        "message": "feat: v0.7.0 - FastAPI RESTful API (TraceID/Metrics/Events/Realtime/PDF報表/RateLimiter)、一鍵全自動部署"
    },
    {
        "tag": "v0.8.0",
        "zip": "student_analytics_v0.8.0_20260906.zip",
        "date": "2026-09-06T23:20:00+08:00",
        "message": "feat: v0.8.0 - 全自動 API 對外穿透通道生成器 (generate_tunnel.py)、多引擎備援、/api/v1/system/tunnel 端點"
    }
]

GITIGNORE_CONTENT = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
.venv/
venv/
ENV/

# Environment Variables
.env
.env.local
.env.*.local
!.env.example

# IDEs and Editors
.vscode/
.idea/
*.swp
*.swo
*~
*.code-workspace

# Logs and databases
*.log
*.sqlite3
*.db
scratch/
temp/
tmp/

# OS specific
.DS_Store
Thumbs.db
desktop.ini

# AI Models (large binaries > 50MB)
*.pt
yolov8m-pose.onnx
models/yolov8m-pose.onnx

# Distribution packages & release archives
releases/
*.zip
*.tar.gz

# Deployment & temporary
.firebase/
.agent/
"""

def get_github_token():
    try:
        import ctypes
        from ctypes import wintypes
        advapi32 = ctypes.windll.advapi32
        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ('Flags', wintypes.DWORD),
                ('Type', wintypes.DWORD),
                ('TargetName', wintypes.LPWSTR),
                ('Comment', wintypes.LPWSTR),
                ('LastWritten', wintypes.FILETIME),
                ('CredentialBlobSize', wintypes.DWORD),
                ('CredentialBlob', ctypes.POINTER(ctypes.c_byte)),
                ('Persist', wintypes.DWORD),
                ('AttributeCount', wintypes.DWORD),
                ('Attributes', ctypes.c_void_p),
                ('TargetAlias', wintypes.LPWSTR),
                ('UserName', wintypes.LPWSTR)
            ]
        PCREDENTIAL = ctypes.POINTER(CREDENTIAL)
        CredReadW = advapi32.CredReadW
        CredReadW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCREDENTIAL)]
        CredReadW.restype = wintypes.BOOL
        CredFree = advapi32.CredFree
        CredFree.argtypes = [ctypes.c_void_p]

        pcred = PCREDENTIAL()
        for target in ['git:https://github.com', 'GitHub - https://api.github.com/4B2G0036']:
            if CredReadW(target, 1, 0, ctypes.byref(pcred)):
                cred = pcred.contents
                size = cred.CredentialBlobSize
                blob = bytes(ctypes.cast(cred.CredentialBlob, ctypes.POINTER(ctypes.c_char * size)).contents.raw)
                CredFree(pcred)
                if b'\x00' in blob:
                    try:
                        token = blob.decode('utf-16le').strip('\x00').strip()
                    except Exception:
                        token = blob.replace(b'\x00', b'').decode('utf-8', errors='ignore').strip()
                else:
                    token = blob.decode('utf-8', errors='ignore').strip()
                token = token.replace('\x00', '').strip()
                if token and len(token) > 10:
                    return token
    except Exception as e:
        print("Error reading token from Windows Credential Manager:", e)
    return None

def run_git(args, cwd=BUILD_DIR, env=None, check=True):
    cmd = [GIT_EXE] + args
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env
    )
    if check and result.returncode != 0:
        print(f"  ⚠️  git {' '.join(args[:4])} failed: {result.stderr.strip()[:200]}")
    return result

def clean_workdir(directory):
    """Clean all files in directory except .git"""
    for entry in os.listdir(directory):
        if entry == ".git":
            continue
        p = os.path.join(directory, entry)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
        except Exception as e:
            print(f"  ⚠️ Error removing {p}: {e}")

def copy_extracted_files(src_root, dst_root):
    """Copy files from src_root to dst_root, flattening any single top directory."""
    # Check if there is a single top-level directory that matches student_analytics_*
    entries = os.listdir(src_root)
    if len(entries) == 1 and os.path.isdir(os.path.join(src_root, entries[0])) and entries[0].startswith("student_analytics_"):
        real_src = os.path.join(src_root, entries[0])
    else:
        real_src = src_root

    # Copy files
    for root, dirs, files in os.walk(real_src):
        # Prune unwanted directories
        dirs[:] = [d for d in dirs if d not in [".git", ".venv", "__pycache__", "scratch", "releases", ".agent", ".firebase"]]
        for f in files:
            # Exclude large models and sensitive files
            if f.endswith(".pt") or f == "yolov8m-pose.onnx" or f == ".env":
                continue
            src_file = os.path.join(root, f)
            rel_path = os.path.relpath(src_file, real_src)
            dst_file = os.path.join(dst_root, rel_path)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            try:
                shutil.copy2(src_file, dst_file)
            except Exception as e:
                pass

def main():
    print("=" * 75)
    print("🚀 學生專注度與異常行為分析系統 — Git 版本歷史重建與 GitHub Push")
    print("=" * 75)

    # 1. Check Git
    if not os.path.exists(GIT_EXE):
        print(f"❌ 找不到 Git: {GIT_EXE}")
        return 1

    # 2. Reset build dir
    if os.path.exists(BUILD_DIR):
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    os.makedirs(BUILD_DIR, exist_ok=True)

    print(f"\n[1/5] 初始化乾淨的 Git 倉庫於: {BUILD_DIR}")
    run_git(["init", "-b", "main"])
    run_git(["config", "user.name", "4B2G0036"])
    run_git(["config", "user.email", "4b2g0036@stust.edu.tw"])
    run_git(["config", "core.autocrlf", "true"])

    # 3. Process each release
    print(f"\n[2/5] 逐版本建立 Commit 與 Release Tags (共 {len(VERSIONS)} 個版本)...")
    temp_extract = os.path.join(ROOT_DIR, "scratch", "temp_extract")

    for i, ver in enumerate(VERSIONS, 1):
        tag = ver["tag"]
        zip_name = ver["zip"]
        date_str = ver["date"]
        msg = ver["message"]
        zip_path = os.path.join(RELEASES_DIR, zip_name)

        print(f"\n  🏷️ [{i}/{len(VERSIONS)}] 處理版本 {tag} ({zip_name})...")
        if not os.path.exists(zip_path):
            print(f"     ⚠️ 找不到檔案 {zip_path}，跳過。")
            continue

        # Clean build working tree (keep .git)
        clean_workdir(BUILD_DIR)

        # Extract zip to temp_extract
        if os.path.exists(temp_extract):
            shutil.rmtree(temp_extract, ignore_errors=True)
        os.makedirs(temp_extract, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(temp_extract)

        # Copy to build dir
        copy_extracted_files(temp_extract, BUILD_DIR)
        shutil.rmtree(temp_extract, ignore_errors=True)

        # Ensure .gitignore
        with open(os.path.join(BUILD_DIR, ".gitignore"), "w", encoding="utf-8") as f:
            f.write(GITIGNORE_CONTENT)

        # Stage all
        run_git(["add", "-A"])

        # Check status
        st = run_git(["status", "--porcelain"], check=False)
        if not st.stdout.strip():
            print(f"     ℹ️ 無變更，略過 commit")
            continue

        # Commit with historical dates
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
        env["GIT_AUTHOR_NAME"] = "4B2G0036"
        env["GIT_AUTHOR_EMAIL"] = "4b2g0036@stust.edu.tw"
        env["GIT_COMMITTER_NAME"] = "4B2G0036"
        env["GIT_COMMITTER_EMAIL"] = "4b2g0036@stust.edu.tw"

        commit_res = run_git(["commit", "-m", msg], env=env)
        if commit_res.returncode == 0:
            print(f"     ✅ Commit: {msg[:60]}...")
            # Tag
            tag_res = run_git(["tag", "-a", tag, "-m", f"Release {tag}"], env=env)
            if tag_res.returncode == 0:
                print(f"     🏷️ Tag {tag} 建立成功")
        else:
            print(f"     ❌ Commit 失敗: {commit_res.stderr.strip()[:100]}")

    # 4. Final working state commit (v0.8.0 latest modifications)
    print(f"\n[3/5] 同步當前工作區最新程式碼與工具檔至倉庫...")
    clean_workdir(BUILD_DIR)

    # Copy current ROOT_DIR to BUILD_DIR
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in [".git", ".venv", "__pycache__", "scratch", "releases", ".agent", ".firebase"]]
        for f in files:
            if f.endswith(".pt") or f == "yolov8m-pose.onnx" or f == ".env":
                continue
            src_file = os.path.join(root, f)
            rel_path = os.path.relpath(src_file, ROOT_DIR)
            dst_file = os.path.join(BUILD_DIR, rel_path)
            os.makedirs(os.path.dirname(dst_file), exist_ok=True)
            try:
                shutil.copy2(src_file, dst_file)
            except Exception:
                pass

    with open(os.path.join(BUILD_DIR, ".gitignore"), "w", encoding="utf-8") as f:
        f.write(GITIGNORE_CONTENT)

    run_git(["add", "-A"])
    final_st = run_git(["status", "--porcelain"], check=False)
    if final_st.stdout.strip():
        env = os.environ.copy()
        now_str = "2026-09-06T23:30:00+08:00"
        env["GIT_AUTHOR_DATE"] = now_str
        env["GIT_COMMITTER_DATE"] = now_str
        env["GIT_AUTHOR_NAME"] = "4B2G0036"
        env["GIT_AUTHOR_EMAIL"] = "4b2g0036@stust.edu.tw"
        env["GIT_COMMITTER_NAME"] = "4B2G0036"
        env["GIT_COMMITTER_EMAIL"] = "4b2g0036@stust.edu.tw"
        run_git(["commit", "-m", "chore: 更新自動穿透腳本、說明文件與部署工具"], env=env)
        print("  ✅ 提交最新工作區更新")

    # 5. Push to GitHub
    print(f"\n[4/5] 連線 GitHub 並推送分支 (main) 與所有版本標籤 (tags)...")
    token = get_github_token()
    if token:
        push_url = f"https://4B2G0036:{token}@github.com/4B2G0036/EdgeAIStudentAnalyticsSystem.git"
        print("  🔑 已獲取授權憑證，正在推送...")
    else:
        push_url = REMOTE_CLEAN_URL
        print("  ⚠️ 未能獲取存儲憑證，嘗試使用預設憑證...")

    run_git(["remote", "remove", "origin"], check=False)
    run_git(["remote", "add", "origin", push_url])

    # Push branch
    push_res = run_git(["push", "-u", "origin", "main", "--force"])
    if push_res.returncode == 0:
        print("  ✅ 分支 main 推送成功！")
    else:
        print(f"  ❌ 分支推送失敗: {push_res.stderr.strip()[:200]}")
        return 1

    # Push tags
    tags_res = run_git(["push", "origin", "--tags", "--force"])
    if tags_res.returncode == 0:
        print("  ✅ 所有版本 Tags 推送成功！")
    else:
        print(f"  ❌ Tags 推送失敗: {tags_res.stderr.strip()[:200]}")

    # Reset remote URL to clean URL (no credentials stored in .git/config)
    run_git(["remote", "set-url", "origin", REMOTE_CLEAN_URL])

    # 6. Replace .git in ROOT_DIR with the clean build
    print(f"\n[5/5] 同步乾淨的 Git 倉庫設定至專案根目錄...")
    target_git = os.path.join(ROOT_DIR, ".git")
    build_git = os.path.join(BUILD_DIR, ".git")

    if os.path.exists(target_git):
        shutil.rmtree(target_git, ignore_errors=True)
    shutil.copytree(build_git, target_git)

    # Clean up build dir
    shutil.rmtree(BUILD_DIR, ignore_errors=True)

    # Verify root git
    run_git(["status"], cwd=ROOT_DIR)
    log_res = run_git(["log", "--oneline", "-n", "15"], cwd=ROOT_DIR)
    print("\n📜 最新 Git Commit 歷史記錄:")
    print(log_res.stdout)

    print("=" * 75)
    print("🎉 恭喜！專案與完整版本 Commit 歷史已成功 Push 到 GitHub！")
    print(f"🌐 倉庫位址: {REMOTE_CLEAN_URL}")
    print("=" * 75)
    return 0

if __name__ == "__main__":
    sys.exit(main())
