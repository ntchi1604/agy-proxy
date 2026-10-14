@echo off
setlocal enabledelayedexpansion

REM ===========================================================================
# Antigravity IDE & Desktop App Language Server Patcher for Windows (CMD)
REM ===========================================================================

set "SCRIPT_DIR=%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%patch_language_server.ps1" %*
if %ERRORLEVEL% neq 0 (
    exit /b %ERRORLEVEL%
)
