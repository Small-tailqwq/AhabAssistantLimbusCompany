@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo ============================================
echo  AALC Manual Update Script
echo ============================================

REM --- Find the update package ---
set "ARCHIVE="
for %%i in (AALC_*.7z) do set "ARCHIVE=%%i"
if not defined ARCHIVE (
    echo [ERROR] No AALC_*.7z found. Place the update package in this directory.
    pause
    exit /b 1
)
echo [!] Found: %ARCHIVE%

REM --- Check prerequisites ---
if not exist "assets\binary\7za.exe" (
    echo [ERROR] This must run from AALC root directory ^(assets\binary\7za.exe missing^)
    pause
    exit /b 1
)

REM --- Step 1: Extract and replace the updater ---
echo [1/3] Extracting AALC Updater.exe from package...
"assets\binary\7za.exe" e "%ARCHIVE%" "AALC Updater.exe" -y >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to extract AALC Updater.exe. Package may be corrupted.
    pause
    exit /b 1
)
echo       Done.

REM --- Step 2: Stage the package ---
echo [2/3] Copying package to update_temp\AALC.7z ...
if not exist "update_temp" mkdir update_temp
copy /y "%ARCHIVE%" "update_temp\AALC.7z" >nul
if errorlevel 1 (
    echo [ERROR] Failed to copy package to update_temp\
    pause
    exit /b 1
)
echo       Done.

REM --- Step 3: Launch updater ---
echo [3/3] Launching updater... ^(AALC will close and reopen automatically^)
echo.
start "" /wait "AALC Updater.exe" "AALC.7z"

echo.
echo Update process completed.
pause
