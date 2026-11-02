param(
    [string]$TargetDir = (Join-Path $env:LOCALAPPDATA "SkillSpector"),
    [switch]$Force
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$Version = "1.1"
$Root = Split-Path -Parent $PSScriptRoot      # 压缩包解压根目录（scripts 的上一级）
if (-not (Test-Path (Join-Path $Root "payload"))) { $Root = $PSScriptRoot }
$Payload = Join-Path $Root "payload"
$AppSrc = Join-Path $Root "app"

function Line { param($t = "") Write-Host $t }
function Step { param($t) Write-Host ""; Write-Host "== $t" -ForegroundColor Cyan }
function Ok   { param($t) Write-Host "  [OK] $t" -ForegroundColor Green }
function Warn { param($t) Write-Host "  [!] $t" -ForegroundColor Yellow }
function Die  {
    param($t)
    Write-Host ""
    Write-Host "  [失败] $t" -ForegroundColor Red
    Write-Host ""
    Write-Host "  安装没有完成。可以把上面的信息截图发给给你安装包的人。" -ForegroundColor Yellow
    exit 1
}

Line ""
Line "  ============================================"
Line "     SkillSpector 体检台  v$Version  安装程序"
Line "  ============================================"
Line ""

# ---------- 1. 环境检测 ----------
Step "1/6  检查环境"

$os = [Environment]::OSVersion.Version
if (-not [Environment]::Is64BitOperatingSystem) { Die "需要在 64 位 Windows 上安装。" }
if ($os.Major -lt 10) { Die "系统版本过低（$os），需要 Windows 10 或更高。" }
Ok "Windows $($os.Major).$($os.Minor)  64 位"

$need = 700
$drive = (Split-Path -Qualifier $TargetDir)
try {
    $free = (New-Object System.IO.DriveInfo($drive)).AvailableFreeSpace / 1MB
} catch { $free = 99999 }
if ($free -lt $need) { Die ("{0} 盘可用空间只有 {1:N0} MB，至少要 {2} MB。" -f $drive, $free, $need) }
Ok ("{0} 盘可用空间 {1:N0} MB" -f $drive, $free)

foreach ($f in @("python.zip", "engine.zip", "run_engine.py")) {
    if (-not (Test-Path (Join-Path $Payload $f))) { Die "安装包不完整，缺少 payload\$f。请重新解压完整压缩包。" }
}
Ok "安装包文件齐全"

# ---------- 2. 旧版本处理 ----------
Step "2/6  检查已有安装"

if (Test-Path $TargetDir) {
    if (-not $Force) {
        Write-Host "  发现已安装：$TargetDir" -ForegroundColor Yellow
        $ans = Read-Host "  要覆盖修复吗？(Y=覆盖  N=退出)"
        if ($ans -notmatch '^[Yy]') { Write-Host "  已取消。"; exit 0 }
    }
    Get-Process SkillSpector-GUI -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
    Remove-Item -Recurse -Force $TargetDir -ErrorAction SilentlyContinue
    Ok "已清理旧安装"
} else {
    Ok "没有旧安装，全新安装"
}

New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $TargetDir "engine") | Out-Null

# ---------- 3. 释放 Python 与引擎 ----------
Step "3/6  释放 Python 运行时（约 70 MB）"

$tar = Join-Path $env:SystemRoot "System32\tar.exe"
function Expand-Zip {
    param($zip, $dest)
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    if (Test-Path $tar) {
        & $tar -xf $zip -C $dest
        if ($LASTEXITCODE -ne 0) { Expand-Archive -Path $zip -DestinationPath $dest -Force }
    } else {
        Expand-Archive -Path $zip -DestinationPath $dest -Force
    }
}

$pyDir = Join-Path $TargetDir "engine\python"
Expand-Zip (Join-Path $Payload "python.zip") $pyDir
if (-not (Test-Path (Join-Path $pyDir "python.exe"))) { Die "Python 释放失败，python.exe 不存在。" }
Ok "Python 就绪"

Step "4/6  释放扫描引擎（约 160 MB，比上一步慢一点）"

$libDir = Join-Path $TargetDir "engine\lib"
Expand-Zip (Join-Path $Payload "engine.zip") $libDir
if (-not (Test-Path (Join-Path $libDir "skillspector"))) { Die "引擎释放失败，lib\skillspector 不存在。" }
Copy-Item (Join-Path $Payload "run_engine.py") (Join-Path $TargetDir "engine\run_engine.py") -Force
Ok "引擎就绪"

# ---------- 4. 自检 ----------
Step "5/6  自检（跑一次引擎版本号）"

$py = Join-Path $pyDir "python.exe"
$runner = Join-Path $TargetDir "engine\run_engine.py"
$verOut = ""
try {
    $verOut = (& $py $runner "--version" 2>&1 | Out-String).Trim()
} catch {
    $verOut = ""
}
if ($verOut -notmatch "SkillSpector") {
    Die "引擎自检失败，输出是：`n$verOut"
}
Ok $verOut

# ---------- 5. 界面 + 快捷方式 ----------
Step "6/6  安装界面程序与快捷方式"

$appDir = Join-Path $TargetDir "app"
New-Item -ItemType Directory -Force -Path $appDir | Out-Null
Copy-Item (Join-Path $AppSrc "*") $appDir -Recurse -Force
$gui = Join-Path $appDir "SkillSpector-GUI.exe"
if (-not (Test-Path $gui)) { Die "界面程序复制失败。" }

$cfg = [ordered]@{
    engine_python = $py
    engine_runner = $runner
    version       = $Version
    installed_at  = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
}
$json = $cfg | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $TargetDir "config.json"), $json, (New-Object System.Text.UTF8Encoding($false)))
Ok "配置写入 config.json"

$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$lnkPath = Join-Path $desktop "SkillSpector 体检台.lnk"
$sc = $ws.CreateShortcut($lnkPath)
$sc.TargetPath = $gui
$sc.WorkingDirectory = $appDir
$sc.IconLocation = "$gui,0"
$sc.Description = "SkillSpector 体检台 - 扫描 AI skill 的安全风险"
$sc.Save()
Ok "桌面快捷方式已创建"

$progs = [Environment]::GetFolderPath("Programs")
$menuDir = Join-Path $progs "SkillSpector"
New-Item -ItemType Directory -Force -Path $menuDir | Out-Null
$sc2 = $ws.CreateShortcut((Join-Path $menuDir "SkillSpector 体检台.lnk"))
$sc2.TargetPath = $gui
$sc2.WorkingDirectory = $appDir
$sc2.IconLocation = "$gui,0"
$sc2.Save()
Ok "开始菜单已创建"

Copy-Item (Join-Path $Root "卸载.bat") $TargetDir -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path (Join-Path $TargetDir "scripts") | Out-Null
Copy-Item (Join-Path $Root "scripts\uninstall.ps1") (Join-Path $TargetDir "scripts") -Force -ErrorAction SilentlyContinue

Line ""
Line "  ============================================"
Line "   安装完成"
Line ""
Line "   桌面已经出现「SkillSpector 体检台」，双击就能用。"
Line "   安装位置：$TargetDir"
Line ""
Line "   提示：第一次扫描会慢一些（要加载分析规则），1-3 分钟正常。"
Line "  ============================================"
Line ""
exit 0
