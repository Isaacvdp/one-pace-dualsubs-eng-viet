@echo off
rem Drag your One Pace video folder onto this file (or double-click and paste the path).
rem Writes copies of the videos with Vietnamese + English subs built in to <folder>\dual\
rem For another arc, change the name below (as written in One Pace's file names).
set "ARC=Dressrosa"

chcp 65001 >nul
set "VIDEOS=%~1"
if "%VIDEOS%"=="" set /p VIDEOS=Video folder:
set "VIDEOS=%VIDEOS:"=%"
if "%VIDEOS:~-1%"=="\" set "VIDEOS=%VIDEOS:~0,-1%"
set "EPS=%~2"
if "%EPS%"=="" set /p EPS=Episodes (e.g. 16-48):
python "%~dp0dualsub.py" mux %EPS% --arc "%ARC%" --video-dir "%VIDEOS%"
pause
