param(
    [string]$TargetDir = (Join-Path $env:LOCALAPPDATA "SkillSpector"),
    [switch]$Force
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

Write-Host ""
Write-Host "  SkillSpector 体检台 卸载" -ForegroundColor Cyan
Write-Host ""
Write-Host "  将删除：$TargetDir"
Write-Host "  以及桌面 / 开始菜单的快捷方式。"
Write-Host ""

if (-not $Force) {
    $ans = Read-Host "  确定卸载吗？(Y/N)"
    if ($ans -notmatch '^[Yy]') { Write-Host "  已取消。"; exit 0 }
}

Get-Process SkillSpector-GUI -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 300

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = Join-Path $desktop "SkillSpector 体检台.lnk"
if (Test-Path $lnk) { Remove-Item $lnk -Force; Write-Host "  已删除桌面快捷方式" -ForegroundColor Green }

$menuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "SkillSpector"
if (Test-Path $menuDir) { Remove-Item $menuDir -Recurse -Force; Write-Host "  已删除开始菜单项" -ForegroundColor Green }

if (Test-Path $TargetDir) {
    Remove-Item $TargetDir -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path $TargetDir) {
        Write-Host "  部分文件删不掉（可能还在使用）。关掉窗口后再运行一次。" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  已删除安装目录" -ForegroundColor Green
}

Write-Host ""
Write-Host "  卸载完成。" -ForegroundColor Green
Write-Host ""
exit 0
