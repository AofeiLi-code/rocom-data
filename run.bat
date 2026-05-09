@echo off
chcp 65001 >nul

:menu
cls
echo.
echo  ============================================
echo    Rocom Helper  v1.1
echo  ============================================
echo    1. Scrape all sprites
echo    2. Check for updates
echo    3. Browse sprites
echo    4. Battle simulator / MCTS AI
echo    5. PVP auto-challenge
echo    6. Exit
echo  ============================================
echo.
set /p choice= Select [1-6]:

if "%choice%"=="1" goto scrape
if "%choice%"=="2" goto check
if "%choice%"=="3" goto view
if "%choice%"=="4" goto battle
if "%choice%"=="5" goto pvp
if "%choice%"=="6" goto end
goto menu

:scrape
echo.
python -X utf8 rocom_scraper.py
echo.
pause
goto menu

:check
echo.
python -X utf8 rocom_scraper.py --check-update --delay 1.5
echo.
pause
goto menu

:view
python -X utf8 viewer.py
goto menu

:battle
python -X utf8 battle.py
goto menu

:pvp
python -X utf8 battle.py --pvp
echo.
pause
goto menu

:end
