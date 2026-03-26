@echo off
chcp 65001 >nul

:menu
cls
echo.
echo  ================================
echo    Rocom Sprite Data Tool
echo  ================================
echo    1. Full scrape (all sprites)
echo    2. Check for updates
echo    3. Exit
echo  ================================
echo.
set /p choice= Select [1-3]:

if "%choice%"=="1" goto scrape
if "%choice%"=="2" goto check
if "%choice%"=="3" goto end
goto menu

:scrape
echo.
python -X utf8 rocom_scraper.py
echo.
pause
goto end

:check
echo.
python -X utf8 rocom_scraper.py --check-update --delay 1.5
echo.
pause
goto end

:end
