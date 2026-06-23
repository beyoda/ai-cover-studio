@echo off
cd /d D:\codex-aivoice
set PYTHONPATH=D:\codex-aivoice\src
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
if "%choice%"=="1" start "" "D:\codex-aivoice\.venv\Scripts\python.exe" -m aivoice_studio.app & exit
if "%choice%"=="2" goto server
if "%choice%"=="3" goto clean
if "%choice%"=="0" exit
goto menu
:server
D:\codex-aivoice\.venv\Scripts\python.exe D:\codex-aivoice\scripts\launch.py
pause >nul
exit
:clean
rmdir /s /q "D:\codex-aivoice\workdir" 2>nul
mkdir "D:\codex-aivoice\workdir" 2>nul
del /q "D:\codex-aivoice\logs\*.log" 2>nul
echo Done. & pause & goto menu
