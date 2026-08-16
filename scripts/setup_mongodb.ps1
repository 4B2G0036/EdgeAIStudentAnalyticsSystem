# =============================================================================
# setup_mongodb.ps1
# 自動安裝 MongoDB 7.0 Community Server (Windows)
# 並驗證 Time Series Collection 支援
# 執行方式：以系統管理員身份執行 PowerShell，然後執行此腳本
# =============================================================================

$ErrorActionPreference = "Stop"

Write-Host "=== MongoDB 7.0 Community Server 安裝腳本 ===" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: 下載 MongoDB 7.0 MSI ──────────────────────────────────────────
$mongoVersion = "7.0.14"
$installerUrl = "https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-$mongoVersion-signed.msi"
$installerPath = "$env:TEMP\mongodb-$mongoVersion.msi"
$mongoDataDir = "C:\data\db"
$mongoLogDir  = "C:\data\log"

if (Get-Command mongod -ErrorAction SilentlyContinue) {
    $v = & mongod --version 2>&1 | Select-String "db version"
    Write-Host "[已安裝] MongoDB: $v" -ForegroundColor Green
} else {
    Write-Host "[Step 1] 下載 MongoDB $mongoVersion MSI..." -ForegroundColor Yellow
    if (!(Test-Path $installerPath)) {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
        Write-Host "  -> 下載完成: $installerPath"
    } else {
        Write-Host "  -> 已存在快取: $installerPath"
    }

    # ── Step 2: 靜默安裝 ───────────────────────────────────────────────────
    Write-Host "[Step 2] 靜默安裝 MongoDB (不含 MongoDB Compass)..." -ForegroundColor Yellow
    $logFile = "$env:TEMP\mongodb_install.log"
    $args = @(
        "/i", $installerPath,
        "/quiet",
        "/norestart",
        "ADDLOCAL=ALL",
        "SHOULD_INSTALL_COMPASS=0",
        "/l*v", $logFile
    )
    $proc = Start-Process msiexec.exe -ArgumentList $args -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Write-Host "[錯誤] MSI 安裝失敗，Exit Code: $($proc.ExitCode)" -ForegroundColor Red
        Write-Host "       請查閱安裝日誌: $logFile"
        exit 1
    }
    Write-Host "  -> 安裝完成" -ForegroundColor Green

    # ── Step 3: 加入 PATH ─────────────────────────────────────────────────
    $mongoBin = "C:\Program Files\MongoDB\Server\7.0\bin"
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($currentPath -notlike "*$mongoBin*") {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$mongoBin", "Machine")
        $env:PATH += ";$mongoBin"
        Write-Host "  -> 已加入 PATH: $mongoBin"
    }
}

# ── Step 3: 建立資料與日誌目錄 ────────────────────────────────────────────
Write-Host "[Step 3] 建立資料目錄..." -ForegroundColor Yellow
foreach ($dir in @($mongoDataDir, $mongoLogDir)) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "  -> 建立: $dir"
    } else {
        Write-Host "  -> 已存在: $dir"
    }
}

# ── Step 4: 建立 mongod.cfg 設定檔 ────────────────────────────────────────
Write-Host "[Step 4] 寫入 mongod.cfg..." -ForegroundColor Yellow
$configPath = "C:\Program Files\MongoDB\Server\7.0\bin\mongod.cfg"
$configContent = @"
systemLog:
  destination: file
  path: C:\data\log\mongod.log
  logAppend: true
storage:
  dbPath: C:\data\db
  journal:
    enabled: true
net:
  bindIp: 127.0.0.1
  port: 27017
"@
Set-Content -Path $configPath -Value $configContent -Encoding UTF8
Write-Host "  -> 已寫入: $configPath"

# ── Step 5: 安裝並啟動 Windows 服務 ───────────────────────────────────────
Write-Host "[Step 5] 安裝 MongoDB 為 Windows 服務..." -ForegroundColor Yellow
$mongodExe = "C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe"
$svcName = "MongoDB"

$existingSvc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if ($existingSvc) {
    Write-Host "  -> 服務已存在，狀態: $($existingSvc.Status)"
    if ($existingSvc.Status -ne "Running") {
        Start-Service -Name $svcName
        Write-Host "  -> 已啟動服務"
    }
} else {
    & $mongodExe --config $configPath --install --serviceName $svcName
    Start-Service -Name $svcName
    Write-Host "  -> MongoDB 服務安裝並啟動完成" -ForegroundColor Green
}

# 設定為自動啟動
Set-Service -Name $svcName -StartupType Automatic
Write-Host "  -> 已設為開機自動啟動"

# ── Step 6: 等待 MongoDB 就緒並驗證版本 ───────────────────────────────────
Write-Host "[Step 6] 等待 MongoDB 就緒..." -ForegroundColor Yellow
$maxWait = 30
$waited = 0
do {
    Start-Sleep -Seconds 2
    $waited += 2
    try {
        $result = & mongosh --quiet --eval "db.runCommand({ping:1}).ok" --host 127.0.0.1:27017 2>&1
        if ($result -eq "1") { break }
    } catch {}
    Write-Host "  ... 等待中 ($waited 秒)"
} while ($waited -lt $maxWait)

if ($waited -ge $maxWait) {
    Write-Host "[警告] MongoDB 超時未回應，請手動確認服務狀態" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== 驗證 MongoDB 版本與 Time Series 支援 ===" -ForegroundColor Cyan

# 取得版本
$version = & mongosh --quiet --eval "db.serverStatus().version" --host 127.0.0.1:27017 2>&1
Write-Host "  MongoDB 版本: $version" -ForegroundColor Green

# 驗證 Time Series Collection 可建立
$tsTest = & mongosh --quiet --host 127.0.0.1:27017 --eval @"
use test_ts_verify;
db.createCollection('ts_verify_temp', {
  timeseries: { timeField: 'timestamp', metaField: 'metadata', granularity: 'seconds' }
});
db.ts_verify_temp.drop();
print('TIME_SERIES_OK');
"@ 2>&1
if ($tsTest -like "*TIME_SERIES_OK*") {
    Write-Host "  Time Series Collection: 支援 ✅" -ForegroundColor Green
} else {
    Write-Host "  Time Series Collection 驗證失敗，請確認版本 >= 7.0" -ForegroundColor Red
    Write-Host "  輸出: $tsTest"
}

Write-Host ""
Write-Host "=== 完成！MongoDB 7.0 已就緒，連線字串: mongodb://127.0.0.1:27017 ===" -ForegroundColor Green
