param(
    [switch]$SkipRagas,
    [int]$Limit = 0
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$sourceDir = 'E:\BaiduNetdiskDownload\育儿\数据\沟通话术'
$env:PYTHONPATH = Join-Path $projectRoot 'backend'

if (-not (Test-Path $sourceDir)) { throw "找不到话术目录：$sourceDir" }
Push-Location $projectRoot
try {
    if (-not $SkipRagas) {
        python -m pip install -r requirements-eval.txt
    }
    python scripts/generate_parenting_ragas_dataset.py --source-dir $sourceDir --copy-to-kb
    python -m scripts.ingest --module '亲子沟通话术' --company-id 1
    $arguments = @('scripts/run_ragas_eval.py')
    if ($SkipRagas) { $arguments += '--skip-ragas' }
    if ($Limit -gt 0) { $arguments += @('--limit', $Limit) }
    python @arguments
} finally {
    Pop-Location
}
