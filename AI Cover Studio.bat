@echo off
cd /d <repo-root>
set PYTHONPATH=<repo-root>\src
:menu
cls
echo   ==============================
echo     AI Cover Studio
echo   ==============================
echo   [1] Desktop App (GUI)
echo   [2] Web Server
echo   [3] Clean Temp Files
echo   [0] Exit
echo.
set /p choice="  Select: "
if "%choice%"=="1" start "" "<repo-root>\.venv\Scripts\python.exe" -m aivoice_studio.app & exit
if "%choice%"=="2" goto server
if "%choice%"=="3" goto clean
if "%choice%"=="0" exit
goto menu
:server
<repo-root>\.venv\Scripts\python.exe <repo-root>\scripts\launch.py
pause >nul
exit
:clean
rmdir /s /q "<repo-root>\workdir" 2>nul
mkdir "<repo-root>\workdir" 2>nul
del /q "<repo-root>\logs\*.log" 2>nul
echo Done. & pause & goto menu
