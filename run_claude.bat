@echo off
setlocal enabledelayedexpansion
title Claude Code with Antigravity Proxy

set "PORT=8000"
set "HOST=127.0.0.1"
set "MODEL=claude-sonnet-4-6"
set "CUSTOM_URL="
set "CLAUDE_ARGS="
set "DANGER_FLAG="

:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="--port" (
    set "PORT=%~2"
    shift & shift
    goto :parse_args
)
if /i "%~1"=="-p" (
    set "PORT=%~2"
    shift & shift
    goto :parse_args
)
if /i "%~1"=="--url" (
    set "CUSTOM_URL=%~2"
    shift & shift
    goto :parse_args
)
if /i "%~1"=="-m" (
    set "MODEL=%~2"
    shift & shift
    goto :parse_args
)
if /i "%~1"=="--model" (
    set "MODEL=%~2"
    shift & shift
    goto :parse_args
)
if /i "%~1"=="--dangerously-skip-permissions" (
    set "DANGER_FLAG=1"
    set "CLAUDE_ARGS=!CLAUDE_ARGS! --dangerously-skip-permissions"
    shift
    goto :parse_args
)
if /i "%~1"=="--danger" (
    set "DANGER_FLAG=1"
    set "CLAUDE_ARGS=!CLAUDE_ARGS! --dangerously-skip-permissions"
    shift
    goto :parse_args
)
if /i "%~1"=="--proxy-help" (
    echo Usage: run_claude.bat [--port PORT] [--url URL] [-m/--model MODEL] [CLAUDE_ARGS...]
    echo Examples:
    echo   run_claude.bat
    echo   run_claude.bat -m claude-sonnet-4-6
    echo   run_claude.bat -m claude-sonnet-4-6-deepagent
    echo   run_claude.bat -m gemini-3.8-flash-high
    echo All other Claude arguments (e.g. -c, -r, -p, doctor) are passed directly to Claude Code.
    exit /b 0
)
if "%~1"=="--" (
    shift
    :collect_rest
    if "%~1"=="" goto :done_args
    set "CLAUDE_ARGS=!CLAUDE_ARGS! %1"
    shift
    goto :collect_rest
)
set "CLAUDE_ARGS=!CLAUDE_ARGS! %1"
shift
goto :parse_args

:done_args
if defined CUSTOM_URL (
    set "ANTHROPIC_BASE_URL=%CUSTOM_URL%"
) else (
    set "ANTHROPIC_BASE_URL=http://%HOST%:%PORT%"
)
set "ANTHROPIC_API_KEY=dummy"
set "ANTHROPIC_MODEL=%MODEL%"
set "ANTHROPIC_SMALL_FAST_MODEL=%MODEL%"
set "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1"

:: Privacy & stability settings (disable non-essential telemetry and window lockouts)
set "DISABLE_TELEMETRY=1"
set "DISABLE_ERROR_REPORTING=1"
set "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"
set "CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1"
set "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1"
if not defined CLAUDE_CODE_MAX_CONTEXT_TOKENS (
    set "CLAUDE_CODE_MAX_CONTEXT_TOKENS=200000"
)

:: Try dynamic model discovery via python, or use curated fallback
set "AGY_SETTINGS="
for /f "delims=" %%i in ('python -c "import urllib.request, json, sys; r = urllib.request.urlopen('http://%HOST%:%PORT%/v1/models', timeout=1.5); data = json.loads(r.read()); models = [m['id'] for m in data.get('data', []) if m['id'].startswith('anthropic.') or m['id'].startswith('claude-')]; print(json.dumps({'availableModels': models}))" 2^>nul') do (
    set "AGY_SETTINGS=%%i"
)

if not defined AGY_SETTINGS (
    set "AGY_SETTINGS={\"availableModels\":[\"claude-sonnet-4-6\",\"claude-sonnet-4-6-deepagent\",\"claude-opus-4-6-deepagent\",\"claude-opus-4-6-thinking\",\"gemini-3.8-flash-high\",\"anthropic.gemini-3.8-flash-high\"]}"
)

:: Auto-permission confirmation prompt if not already set
if not defined DANGER_FLAG (
    echo !CLAUDE_ARGS! | findstr /i /c:"--dangerously-skip-permissions" /c:"--permission-mode" >nul
    if !ERRORLEVEL! neq 0 (
        echo.
        set /p "PERM_CHOICE=Enable auto-approval of actions without prompts? (--dangerously-skip-permissions) [y/N]: "
        if /i "!PERM_CHOICE!"=="y" (
            set "CLAUDE_ARGS=!CLAUDE_ARGS! --dangerously-skip-permissions"
        )
    )
)

echo ===================================================
echo   Launching Claude Code with Antigravity Proxy
echo   * URL:   %ANTHROPIC_BASE_URL%
echo   * Model: %ANTHROPIC_MODEL%
echo ===================================================

where claude >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] 'claude' CLI was not found. Install it via: npm install -g @anthropic-ai/claude-code
    pause
    exit /b 1
)

claude --settings "%AGY_SETTINGS%" %CLAUDE_ARGS%
