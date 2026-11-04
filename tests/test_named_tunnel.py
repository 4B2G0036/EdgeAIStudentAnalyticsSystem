"""
test_named_tunnel.py
=====================
具名 Tunnel 支援的單元 / 整合測試 (不需 Cloudflare 帳號)：
  1. 設定解析：token + URL 皆齊備才啟用，缺一退回 Quick Tunnel
  2. token 以環境變數傳遞，不得出現在命令列與日誌
  3. 啟動失敗 (無效 token / 無法執行) 時能回報錯誤而非卡住
  4. ensure_tunnel 在具名模式失敗時退回 Quick Tunnel；模式切換不沿用舊通道
執行: python tests/test_named_tunnel.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import service_manager as sm  # noqa: E402

_results = []


def check(name, cond, extra=""):
    _results.append(bool(cond))
    print(f"  {'✓' if cond else '✗'} {name} {extra}")


def with_env(env_text, fn):
    """以暫時 .env 與乾淨環境變數執行 fn"""
    saved_env_file = sm.ENV_FILE
    saved = {k: os.environ.pop(k, None) for k in ("CLOUDFLARE_TUNNEL_TOKEN", "TUNNEL_PUBLIC_URL")}
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as f:
        f.write(env_text)
        path = f.name
    sm.ENV_FILE = path
    try:
        return fn()
    finally:
        sm.ENV_FILE = saved_env_file
        os.unlink(path)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_config_parsing():
    print("[1] 設定解析")
    check("無設定 -> None (Quick Tunnel)", with_env("MONGO_URI=x\n", sm.named_tunnel_config) is None)
    check("只有 token -> None", with_env("CLOUDFLARE_TUNNEL_TOKEN=abc\n", sm.named_tunnel_config) is None)
    check("只有 URL -> None", with_env("TUNNEL_PUBLIC_URL=https://api.example.com\n", sm.named_tunnel_config) is None)
    check("空值 -> None", with_env("CLOUDFLARE_TUNNEL_TOKEN=\nTUNNEL_PUBLIC_URL=\n", sm.named_tunnel_config) is None)
    check("註解行不生效", with_env("#CLOUDFLARE_TUNNEL_TOKEN=abc\n#TUNNEL_PUBLIC_URL=https://a.b\n", sm.named_tunnel_config) is None)
    cfg = with_env('CLOUDFLARE_TUNNEL_TOKEN="tok123"\nTUNNEL_PUBLIC_URL=https://api.example.com/\n', sm.named_tunnel_config)
    check("兩者齊備 -> (token, url)，去除引號與結尾斜線", cfg == ("tok123", "https://api.example.com"), str(cfg))
    cfg = with_env("CLOUDFLARE_TUNNEL_TOKEN=t\nTUNNEL_PUBLIC_URL=api.example.com\n", sm.named_tunnel_config)
    check("未帶協定時補上 https://", cfg == ("t", "https://api.example.com"), str(cfg))
    cfg = with_env("CLOUDFLARE_TUNNEL_TOKEN=t\nTUNNEL_PUBLIC_URL=http://api.example.com\n", sm.named_tunnel_config)
    check("http 強制升級為 https", cfg == ("t", "https://api.example.com"), str(cfg))
    os.environ["CLOUDFLARE_TUNNEL_TOKEN"] = "envtok"
    os.environ["TUNNEL_PUBLIC_URL"] = "https://env.example.com"
    try:
        cfg = with_env("CLOUDFLARE_TUNNEL_TOKEN=filetok\nTUNNEL_PUBLIC_URL=https://file.example.com\n", sm.named_tunnel_config)
        # with_env clears env vars first, so .env wins here; verify env var priority separately
        check(".env 設定可被讀取", cfg == ("filetok", "https://file.example.com"))
        check("環境變數優先於 .env", sm.read_env_value("CLOUDFLARE_TUNNEL_TOKEN") == "envtok")
    finally:
        os.environ.pop("CLOUDFLARE_TUNNEL_TOKEN", None)
        os.environ.pop("TUNNEL_PUBLIC_URL", None)


def test_token_not_leaked_and_invalid_token_fails():
    print("[2] 無效 token 啟動：回報錯誤、token 不外洩")
    secret = "eyJhIjoiVEVTVC1TRUNSRVQtVE9LRU4tMTIzNDU2Iiwid"  # 非有效 token
    log_before = os.path.getsize(sm.TUNNEL_LOG) if os.path.exists(sm.TUNNEL_LOG) else 0
    pid, err = sm.start_named_tunnel(secret, timeout=40)
    check("無效 token 回報錯誤 (pid=None)", pid is None and bool(err), f"err={err!r}")
    with open(sm.TUNNEL_LOG, "r", encoding="utf-8", errors="replace") as f:
        f.seek(log_before)
        new_log = f.read()
    check("日誌不含 token", secret not in new_log)
    check("日誌 header 不含 token 參數", "--token" not in new_log)


def test_fallback_to_quick_on_named_failure():
    print("[3] 具名 Tunnel 失敗 -> 自動退回 Quick Tunnel (以模擬函式驗證流程)")
    calls = []
    orig = (sm.named_tunnel_config, sm.start_named_tunnel, sm.start_tunnel, sm.wait_tunnel_reachable,
            sm.publish_api_url, sm.read_status, sm.kill_process_tree)
    try:
        sm.named_tunnel_config = lambda: ("tok", "https://api.example.com")
        sm.start_named_tunnel = lambda t, timeout=60: (calls.append("named") or (None, "boom"))
        sm.start_tunnel = lambda timeout=45: (calls.append("quick") or (111, "https://x.trycloudflare.com"))
        sm.wait_tunnel_reachable = lambda u, timeout=45: True
        sm.publish_api_url = lambda url, engine, pid: calls.append(("publish", url, engine))
        sm.read_status = lambda: {}
        sm.kill_process_tree = lambda pid: None
        url = sm.ensure_tunnel()
        check("具名重試 3 次後退回 Quick", calls.count("named") == 3 and "quick" in calls, str(calls))
        check("最終回傳 Quick 網址", url == "https://x.trycloudflare.com")
        check("發佈的引擎為 Quick Tunnel", ("publish", url, "Cloudflare Tunnel") in calls)

        # 具名成功
        calls.clear()
        sm.start_named_tunnel = lambda t, timeout=60: (calls.append("named") or (222, None))
        url = sm.ensure_tunnel()
        check("具名成功回傳固定網址且不啟動 Quick", url == "https://api.example.com" and "quick" not in calls, str(calls))
        check("發佈的引擎為 Named Tunnel", ("publish", url, "Cloudflare Named Tunnel") in calls)

        # 模式切換：舊狀態為 Quick，現在設定具名 -> 不可沿用
        calls.clear()
        sm.read_status = lambda: {"engine": "Cloudflare Tunnel", "tunnel_url": "https://old.trycloudflare.com", "pid": 1}
        sm.pid_alive = lambda pid: True
        sm.tunnel_healthy = lambda u, timeout=6.0: True
        url = sm.ensure_tunnel()
        check("Quick -> Named 切換不沿用舊通道", url == "https://api.example.com", str(url))
    finally:
        (sm.named_tunnel_config, sm.start_named_tunnel, sm.start_tunnel, sm.wait_tunnel_reachable,
         sm.publish_api_url, sm.read_status, sm.kill_process_tree) = orig


if __name__ == "__main__":
    print("=" * 60)
    test_config_parsing()
    test_token_not_leaked_and_invalid_token_fails()
    test_fallback_to_quick_on_named_failure()
    print("=" * 60)
    if all(_results):
        print(f"🎉 ALL TESTS PASSED! ({len(_results)})")
    else:
        print(f"❌ {_results.count(False)} FAILED / {len(_results)}")
        sys.exit(1)

