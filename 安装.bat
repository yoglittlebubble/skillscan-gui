@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SkillSpector 体检台 - 安装
color 07
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
echo.
echo   按任意键关闭这个窗口。
pause >nul
