# 售后智能助手 — Windows 一键启动脚本
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  售后智能助手 — 启动中..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$backendPort = 5002
if (Get-NetTCPConnection -LocalPort $backendPort -State Listen -ErrorAction SilentlyContinue) {
    $backendPort = 5003
    Write-Host "端口 5002 已被占用，后端将使用端口 $backendPort" -ForegroundColor Yellow
}

# Load .env for child processes when present
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) { return }
        $key, $value = $line.Split("=", 2)
        if ($key -and -not (Test-Path "env:$key")) {
            [Environment]::SetEnvironmentVariable($key.Trim(), $value.Trim().Trim('"').Trim("'"), "Process")
        }
    }
    Write-Host "已加载 .env 环境变量" -ForegroundColor Green
}

# Check environment variables
$required = @("DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY")
$missing = @()
foreach ($var in $required) {
    if (-not (Test-Path "env:$var")) {
        $missing += $var
    }
}
if ($missing.Count -gt 0) {
    Write-Host "  缺少环境变量: $($missing -join ', ')" -ForegroundColor Yellow
    Write-Host "  请复制 .env.example 为 .env 并填写后重试" -ForegroundColor Yellow
}

# Start Backend
Write-Host "[1/2] 启动 FastAPI 后端 (端口 $backendPort)..." -ForegroundColor Green
Start-Process powershell -ArgumentList @"
    -NoExit -Command `
    cd '$PSScriptRoot\backend'; `
    `$env:PYTHONUNBUFFERED='1'; `
    pip install -r requirements.txt -q; `
    Write-Host 'FastAPI running at http://localhost:$backendPort'; `
    Write-Host 'API Docs at http://localhost:$backendPort/docs'; `
    Write-Host 'Request and RAGAS logs will be shown below'; `
    uvicorn app.main:app --host 0.0.0.0 --port $backendPort --log-level info --access-log
"@

Start-Sleep -Seconds 3

# Start Frontend
Write-Host "[2/2] 启动 Vue 前端开发服务 (端口 5173)..." -ForegroundColor Green
Start-Process powershell -ArgumentList @"
    -NoExit -Command `
    cd '$PSScriptRoot\frontend'; `
    `$env:BACKEND_PORT='$backendPort'; `
    npm install; `
    Write-Host 'Vue Dev Server running at http://localhost:5173'; `
    npm run dev
"@

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  启动完成!" -ForegroundColor Green
Write-Host "  前端: http://localhost:5173" -ForegroundColor Green
Write-Host "  后端: http://localhost:$backendPort" -ForegroundColor Green
Write-Host "  API文档: http://localhost:$backendPort/docs" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "按任意键退出..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
