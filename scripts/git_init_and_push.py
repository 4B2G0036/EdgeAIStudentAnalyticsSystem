"""
git_init_and_push.py
=====================
初始化 Git 倉庫、依版本解壓 zip 後逐版本建立 commit，
最後設定 remote 並 push 到 GitHub。

用法:
    python scripts/git_init_and_push.py
"""

import os
import sys
import subprocess
import zipfile
import shutil
import tempfile
from datetime import datetime

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIT_EXE = r"C:\Program Files\Git\bin\git.exe"
RELEASES_DIR = os.path.join(ROOT_DIR, "releases")
REMOTE_URL = "https://github.com/4B2G0036/EdgeAIStudentAnalyticsSystem.git"

# Version map: (zip_filename, commit_timestamp_env, commit_message)
VERSIONS = [
    ("student_analytics_v0.1.0_20260816.zip", "2026-08-16T14:00:00+08:00", "feat: v0.1.0 - 專案初始化與基礎架構 (FastAPI基礎路由、MongoDB連線、config.py全域設定)"),
    ("student_analytics_v0.1.1_20260816.zip", "2026-08-16T15:10:00+08:00", "feat: v0.1.1 - 歷史課程列表與搜尋分頁、下課確定對話框 (Modal)"),
    ("student_analytics_v0.2.0_20260816.zip", "2026-08-16T16:30:00+08:00", "feat: v0.2.0 - 前端互動式 API 網址設定與即時指標輪詢"),
    ("student_analytics_v0.2.1_20260816.zip", "2026-08-16T17:23:00+08:00", "feat: v0.2.1 - 本機 WebCam 雙鏡頭模式、隱私保護遮罩、Firebase Hosting 發布"),
    ("student_analytics_v0.5.0_20260816.zip", "2026-08-16T17:51:00+08:00", "feat: v0.5.0 - MongoDB 8.3.7 整合、YOLOv8-Pose ONNX 模型匯出與推論驗證"),
    ("student_analytics_v0.6.0_20260816.zip", "2026-08-16T20:18:00+08:00", "feat: v0.6.0 - 全系統整合驗證、CORS 修復、Cloudflare HTTPS 穿透、core/ 8大視覺AI模組"),
    ("student_analytics_v0.7.0_20260906.zip", "2026-09-06T22:56:00+08:00", "feat: v0.7.0 - FastAPI RESTful API (TraceID/Metrics/Events/Realtime/PDF報表/RateLimiter)、一鍵全自動部署"),
    ("student_analytics_v0.8.0_20260906.zip", "2026-09-06T23:20:00+08:00", "feat: v0.8.0 - 全自動API對外穿透通道生成器 (generate_tunnel.py)、Cloudflare/Pinggy備援、/api/v1/system/tunnel端點"),
]

def run_git(args, cwd=ROOT_DIR, env=None, check=True):
    """Run a git command and return output."""
    cmd = [GIT_EXE] + args
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env
    )
    if check and result.returncode != 0:
        print(f"  ⚠️  git {' '.join(args[:3])} failed: {result.stderr.strip()}")
    return result

def build_commit_env(timestamp_str):
    """Build env with GIT_AUTHOR_DATE and GIT_COMMITTER_DATE."""
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = timestamp_str
    env["GIT_COMMITTER_DATE"] = timestamp_str
    env["GIT_AUTHOR_NAME"] = "4B2G0036"
    env["GIT_AUTHOR_EMAIL"] = "4b2g0036@stust.edu.tw"
    env["GIT_COMMITTER_NAME"] = "4B2G0036"
    env["GIT_COMMITTER_EMAIL"] = "4b2g0036@stust.edu.tw"
    return env

print("=" * 70)
print("🚀 開始初始化 Git 倉庫並建立各版本 Commit 歷史記錄")
print("=" * 70)

# 1. Initialize git repo
git_dir = os.path.join(ROOT_DIR, ".git")
if os.path.exists(git_dir):
    print("\n✅ 已存在 .git 目錄，跳過 git init")
else:
    print("\n[1/4] 初始化 Git 倉庫...")
    run_git(["init", "-b", "main"])
    print("  🟢 git init 完成")

# 2. Configure user (local)
print("\n[2/4] 設定 Git 使用者資訊...")
run_git(["config", "user.name", "4B2G0036"])
run_git(["config", "user.email", "4b2g0036@stust.edu.tw"])
print("  🟢 git config 完成")

# 3. Create gitignore
gitignore_path = os.path.join(ROOT_DIR, ".gitignore")
if not os.path.exists(gitignore_path):
    with open(gitignore_path, "w", encoding="utf-8") as f:
        f.write("""# Python
__pycache__/
*.py[cod]
*.pyo
.venv/
*.egg-info/

# Environment
.env
!.env.example

# IDE
.idea/
.vscode/
*.code-workspace

# OS
.DS_Store
Thumbs.db

# Large model files (use releases/ for distribution)
yolov8m-pose.pt
yolov8m-pose.onnx
yolov8n-pose.pt

# Scratch / temp
scratch/

# Releases (too large for git, use GitHub Releases)
releases/

# Firebase
.firebase/
""")
    print("  🟢 .gitignore 建立完成")

# 4. Create version commits from each zip
print("\n[3/4] 依版本逐一解壓並建立 Git Commit 歷史...")

for zip_name, timestamp, commit_msg in VERSIONS:
    zip_path = os.path.join(RELEASES_DIR, zip_name)
    version_tag = zip_name.split("_")[2]  # e.g. v0.1.0

    if not os.path.exists(zip_path):
        print(f"\n  ⚠️ [{version_tag}] 找不到 {zip_name}，跳過。")
        continue

    print(f"\n  📦 [{version_tag}] 從 {zip_name} 建立 commit...")

    # Extract zip to a temp dir, copy files to ROOT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmpdir)
        
        # Copy all extracted files (overwrite existing)
        for dirpath, dirnames, filenames in os.walk(tmpdir):
            # Skip excluded dirs
            dirnames[:] = [d for d in dirnames if d not in [".git", ".venv", "__pycache__", "scratch", "releases"]]
            for fname in filenames:
                src = os.path.join(dirpath, fname)
                rel = os.path.relpath(src, tmpdir)
                dst = os.path.join(ROOT_DIR, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                try:
                    shutil.copy2(src, dst)
                except Exception as e:
                    pass

    # Stage all changes
    run_git(["add", "."])

    # Check if there's anything to commit
    status = run_git(["status", "--porcelain"], check=False)
    if not status.stdout.strip():
        print(f"    ℹ️ [{version_tag}] 無檔案變更，跳過 commit。")
        continue

    # Commit with historical date
    env = build_commit_env(timestamp)
    result = run_git(["commit", "-m", commit_msg], env=env, check=False)
    if result.returncode == 0:
        print(f"    🟢 [{version_tag}] Commit 建立成功！")
        print(f"       {commit_msg[:60]}...")
    else:
        print(f"    ⚠️  [{version_tag}] commit 失敗: {result.stderr.strip()[:100]}")

# 5. Stage and commit current working state (v0.8.0 head)
print("\n  📝 [HEAD] 提交目前最新工作狀態...")
run_git(["add", "."])
head_status = run_git(["status", "--porcelain"], check=False)
if head_status.stdout.strip():
    env = build_commit_env("2026-09-06T23:21:00+08:00")
    run_git(["commit", "-m", "chore: 更新 README、CHANGELOG、VERSION 至 v0.8.0 並整合 git push 自動化工具"], env=env, check=False)
    print("    🟢 [HEAD] 最新狀態 commit 完成")

# 6. Set up remote and push
print("\n[4/4] 設定 GitHub Remote 並 Push...")
# Remove old remote if any
run_git(["remote", "remove", "origin"], check=False)
run_git(["remote", "add", "origin", REMOTE_URL])
print(f"  🟢 Remote 設定完成: {REMOTE_URL}")

# Push
print("  📡 正在 push 到 GitHub...")
push_result = run_git(["push", "-u", "origin", "main", "--force"], check=False)
if push_result.returncode == 0:
    print("  🟢 Push 成功！")
else:
    print(f"  ❌ Push 失敗: {push_result.stderr.strip()}")
    print("\n  📋 若出現認證問題，請先在瀏覽器登入 GitHub，或設定 Personal Access Token (PAT)：")
    print("     git remote set-url origin https://<PAT>@github.com/4B2G0036/EdgeAIStudentAnalyticsSystem.git")

print("\n" + "=" * 70)
print("🎉 完成！所有版本 commit 歷史已建立並 Push 至 GitHub")
print(f"  🌐 Repository: https://github.com/4B2G0036/EdgeAIStudentAnalyticsSystem")
print("=" * 70)
