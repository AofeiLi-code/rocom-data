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
echo    3. Browse sprites (viewer)
echo    4. Battle simulator
echo    5. Exit
echo  ================================
echo.
set /p choice= Select [1-5]:

if "%choice%"=="1" goto scrape
if "%choice%"=="2" goto check
if "%choice%"=="3" goto view
if "%choice%"=="4" goto battle
if "%choice%"=="5" goto end
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

:view
python -X utf8 viewer.py
goto end

:battle
python -X utf8 battle.py
goto end

:end
