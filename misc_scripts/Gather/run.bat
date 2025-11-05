@echo off

:: 1. Check for Administrator privileges
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"

:: 2. If not admin, re-launch this script as admin
if '%errorlevel%' NEQ '0' (
    echo Requesting Administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit
)

:: 3. If we are here, we ARE an administrator.
echo Administrator privileges confirmed.
echo Starting Orion Gather Bot...

:: Set the path to your Python (if it's not in your system PATH,
:: you might need the full path, e.g., C:\Users\migue\...\python.exe)
set PYTHON_EXE=python

:: Set the directory of this batch file
set SCRIPT_DIR=%~dp0

:: 4. Run the bot
echo Running bot from: %SCRIPT_DIR%
cd /d %SCRIPT_DIR%
%PYTHON_EXE% -m bot.main_app

:: 5. Keep the window open after the script finishes
echo.
echo Bot script has finished or was stopped.
pause