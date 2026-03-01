"""Onboarding setup endpoint — returns everything a developer needs to get started."""

from pathlib import Path

from fastapi import APIRouter

router = APIRouter(tags=["Onboarding"])


@router.get("/onboarding/setup")
async def get_onboarding_setup() -> dict:
    """Return the Claude Code batch file and setup instructions pre-configured for this PeaRL instance."""
    from pearl.config import settings

    # Resolve API URL — use configured host/port
    api_url = f"http://localhost:{settings.port}/api/v1"

    # Resolve pearl_dev src path
    if settings.pearl_src_path:
        src_path = settings.pearl_src_path
    else:
        src_path = str(Path(__file__).resolve().parents[3])

    # Resolve python path — prefer venv python alongside this install
    venv_python = Path(src_path).parent / ".venv" / "bin" / "python"
    python_path = str(venv_python) if venv_python.exists() else "/usr/bin/python3"

    bat_file = f"""@echo off
title Claude Code

:: If a folder was passed as argument (e.g. drag-drop), use it
if not "%~1"=="" (
    set "TARGET=%~1"
    goto :launch
)

:: Otherwise, open folder browser starting at Development folder
set "psCmd=$app = New-Object -ComObject Shell.Application; $folder = $app.BrowseForFolder(0, 'Select project folder for Claude Code', 0x0050, 'C:\\Users\\%USERNAME%\\Development'); if ($folder) {{ $folder.Self.Path }} else {{ 'CANCELLED' }}"

for /f "delims=" %%i in ('powershell -NoProfile -Command "%psCmd%"') do set "TARGET=%%i"

if "%TARGET%"=="CANCELLED" (
    echo No folder selected. Exiting.
    pause
    exit /b 1
)

:launch
echo Starting Claude Code in: %TARGET%
set "WSL_PATH=%TARGET:\\=/%"
set "WSL_PATH=%WSL_PATH:C:=/mnt/c%"

:: Write .mcp.json if missing so PeaRL MCP tools are available from first prompt
wsl -d Ubuntu -- bash -lc "test -f '%WSL_PATH%/.mcp.json'" 2>nul
if %ERRORLEVEL%==1 (
    wsl -d Ubuntu -- bash -lc "printf '{{\"mcpServers\":{{\"pearl\":{{\"command\":\"{python_path}\",\"args\":[\"-m\",\"pearl_dev.unified_mcp\",\"--directory\",\".\",\"--api-url\",\"{api_url}\"],\"env\":{{\"PYTHONPATH\":\"{src_path}\"}}}}}}}}\\n' > '%WSL_PATH%/.mcp.json'"
    echo   PeaRL MCP configured.
)

:: PeaRL: auto-register if .pearl.yaml exists
wsl -d Ubuntu -- bash -lc "{python_path} {src_path}/../scripts/pearl_hook_check.py --cwd '%WSL_PATH%'" 2>nul

:: New project hint if no .pearl.yaml
wsl -d Ubuntu -- bash -lc "test -f '%WSL_PATH%/.pearl.yaml'" 2>nul
if %ERRORLEVEL%==1 (
    echo.
    echo ================================================================
    echo  NEW PROJECT - paste this into Claude Code to get started:
    echo.
    echo  Register this project in PeaRL using the createProject MCP
    echo  tool, then fetch .pearl.yaml and .mcp.json from the API and
    echo  save both to this folder. Then build the app per CLAUDE.md.
    echo ================================================================
    echo.
    pause
)

wsl -d Ubuntu -- bash -lc "cd '%WSL_PATH%' && claude"
"""

    instructions = [
        {
            "step": 1,
            "title": "Download the batch file",
            "detail": "Save claude-code.bat from the 'bat_file' field to a convenient location (e.g. C:\\Users\\<you>\\Development\\Claude Code.bat)",
        },
        {
            "step": 2,
            "title": "Double-click to launch",
            "detail": "A folder browser opens. Select your project folder and confirm.",
        },
        {
            "step": 3,
            "title": "First launch of a new project",
            "detail": "The batch file writes .mcp.json automatically so PeaRL MCP tools are available immediately. Paste the shown prompt into Claude Code to register the project.",
        },
        {
            "step": 4,
            "title": "Subsequent launches",
            "detail": "If .pearl.yaml exists the project is auto-registered silently and Claude Code opens with no extra steps.",
        },
        {
            "step": 5,
            "title": "Get project config files",
            "detail": f"After registering a project, download its config files: GET {api_url}/projects/{{project_id}}/pearl.yaml and GET {api_url}/projects/{{project_id}}/mcp.json",
        },
    ]

    return {
        "api_url": api_url,
        "bat_filename": "Claude Code.bat",
        "bat_file": bat_file,
        "instructions": instructions,
        "python_path": python_path,
        "pearl_src_path": src_path,
    }
