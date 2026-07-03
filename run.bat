@echo off
rem Real double-click entry point for Windows (docs/13 M18 "zero-CLI" launch).
rem
rem Double-clicking run.py directly hands it to whatever Python is
rem file-associated on this machine (often a bare system install with none
rem of this project's dependencies) -- it fails on the first import and the
rem console window closes itself the instant the process exits, so it looks
rem like nothing happened. This wrapper calls the project's own .venv
rem explicitly and keeps the window open if anything goes wrong.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   Obsidian Desk hasn't been set up on this machine yet.
    echo   From this folder, open a terminal and run:
    echo.
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -e ".[ui,search,dev]"
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" run.py %*

if errorlevel 1 (
    echo.
    echo   Obsidian Desk exited with an error ^(see above^).
    pause
)
endlocal
