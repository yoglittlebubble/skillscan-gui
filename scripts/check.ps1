param(
    [string]$TargetDir = (Join-Path $env:LOCALAPPDATA "SkillSpector")
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$bad = 0
function Line { param($t = "") Write-Host $t }
function Good { param($t) Write-Host "  [OK]  $t" -ForegroundColor Green }
function Bad  { param($t) Write-Host "  [X]   $t" -ForegroundColor Red; $script:bad++ }
function Info { param($t) Write-Host "        $t" -ForegroundColor DarkGray }

Line ""
Line "  ============================================"
Line "     SkillSpector 体检台  环境检测"
Line "  ============================================"
Line ""

Line "  安装位置：$TargetDir"
Line ""

# 1. 系统
if ([Environment]::Is64BitOperatingSystem) { Good "64 位 Windows" } else { Bad "不是 64 位 Windows" }
$os = [Environment]::OSVersion.Version
if ($os.Major -ge 10) { Good ("Windows {0}.{1}" -f $os.Major, $os.Minor) } else { Bad "Windows 版本过低" }

# 2. 安装目录与配置
$cfgPath = Join-Path $TargetDir "config.json"
if (Test-Path $cfgPath) {
    Good "配置文件存在"
    try {
        $cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        Bad "配置文件读不了（可能损坏）"
        $cfg = $null
    }
} else {
    Bad "没有配置文件 config.json —— 还没装过，或装坏了"
    $cfg = $null
}

$py = $null; $runner = $null
if ($cfg) {
    $py = $cfg.engine_python
    $runner = $cfg.engine_runner
} else {
    $py = Join-Path $TargetDir "engine\python\python.exe"
    $runner = Join-Path $TargetDir "engine\run_engine.py"
}

if ($py -and (Test-Path $py)) { Good "Python 运行时：$py" } else { Bad "找不到 Python 运行时：$py" }
if ($runner -and (Test-Path $runner)) { Good "引擎启动器：$runner" } else { Bad "找不到引擎启动器：$runner" }
$lib = Join-Path $TargetDir "engine\lib\skillspector"
if (Test-Path $lib) { Good "引擎依赖包完整" } else { Bad "引擎依赖包缺失（engine\lib\skillspector）" }

# 3. 界面
$gui = Join-Path $TargetDir "app\SkillSpector-GUI.exe"
if (Test-Path $gui) { Good "界面程序：$gui" } else { Bad "找不到界面程序：$gui" }

# 4. 快捷方式
$lnk = Join-Path ([Environment]::GetFolderPath("Desktop")) "SkillSpector 体检台.lnk"
if (Test-Path $lnk) { Good "桌面快捷方式" } else { Bad "桌面快捷方式不存在（可以手动把 app\SkillSpector-GUI.exe 发到桌面）" }

# 5. 真跑一次
if ($py -and $runner -and (Test-Path $py) -and (Test-Path $runner)) {
    Line ""
    Line "  正在试跑引擎…"
    $out = (& $py $runner "--version" 2>&1 | Out-String).Trim()
    if ($out -match "SkillSpector") { Good "引擎可以运行：$out" } else { Bad "引擎跑不起来"; Info $out }
}

# 6. 磁盘空间
try {
    $free = (New-Object System.IO.DriveInfo((Split-Path -Qualifier $TargetDir))).AvailableFreeSpace / 1MB
    if ($free -gt 200) { Good ("剩余空间 {0:N0} MB" -f $free) } else { Bad ("剩余空间不足：{0:N0} MB" -f $free) }
} catch {}

Line ""
if ($bad -eq 0) {
    Write-Host "  一切正常，可以直接用。" -ForegroundColor Green
    Line ""
    exit 0
} else {
    Write-Host "  发现 $bad 个问题。" -ForegroundColor Red
    Write-Host "  解决办法：重新运行压缩包里的「安装.bat」覆盖修复（选 Y）。" -ForegroundColor Yellow
    Line ""
    exit 1
}
