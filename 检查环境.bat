@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SkillSpector 体检台 - 环境检测
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\check.ps1"
echo.
echo   按任意键关闭这个窗口。
pause >nul
