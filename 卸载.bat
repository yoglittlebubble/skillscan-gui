@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SkillSpector 体检台 - 卸载
if exist "%~dp0scripts\uninstall.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\scripts\uninstall.ps1"
)
echo.
echo   按任意键关闭这个窗口。
pause >nul
