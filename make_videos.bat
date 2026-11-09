@echo off
rem Drag a folder with One Pace videos onto this file (or double-click it and paste the path).
rem Copies of the videos with Vietnamese + English subtitles are written to <folder>\dual\
rem The arc is read from the folder name, e.g. "[One Pace][823-902] Whole Cake Island [720p]".

chcp 65001 >nul
set "VIDEOS=%~1"
if "%VIDEOS%"=="" set /p VIDEOS=Video folder:
set "VIDEOS=%VIDEOS:"=%"
if "%VIDEOS:~-1%"=="\" set "VIDEOS=%VIDEOS:~0,-1%"
set "EPS=%~2"
if "%EPS%"=="" set /p EPS=Episodes (e.g. 1-19), or press Enter for all:
if "%EPS%"=="" set "EPS=all"
python "%~dp0dualsub.py" mux %EPS% --video-dir "%VIDEOS%"
pause
