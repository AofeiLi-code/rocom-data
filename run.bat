@echo off
chcp 65001 >nul

:menu
cls
echo.
echo  ============================================
echo    Rocom Helper  v1.3
echo  ============================================
echo    1. Scrape sprites              (rocom wiki)
echo    2. Check for sprite updates
echo    3. Scrape BWIKI lineups        (player teams)
echo    4. Browse sprites              (viewer)
echo    5. Battle simulator            (teams / import / PVP / LLM review)
echo    6. Train MCTS                  (self-play loop)
echo    7. Manage experience DB
echo    0. Exit
echo  ============================================
echo.
set /p choice= Select [0-7]:

if "%choice%"=="1" goto scrape
if "%choice%"=="2" goto check
if "%choice%"=="3" goto lineups
if "%choice%"=="4" goto view
if "%choice%"=="5" goto battle
if "%choice%"=="6" goto train
if "%choice%"=="7" goto dbmanage
if "%choice%"=="0" goto end
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

:lineups
echo.
python -X utf8 lineup_scraper.py
echo.
pause
goto menu

:view
python -X utf8 viewer.py
goto menu

:battle
python -X utf8 battle.py
goto menu

:train
python -X utf8 train.py
echo.
pause
goto menu

:dbmanage
python -X utf8 db_manage.py
echo.
pause
goto menu

:end
