@echo off
setlocal
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "PYTHONPATH=%ROOT%\src"
cd /d "%ROOT%"

if not exist "%PYTHON%" (
  echo.
  echo   Python environment not found: "%PYTHON%"
  echo   Create it first:
  echo     python -m venv .venv
  echo     .venv\Scripts\activate
  echo     pip install -e .
  echo.
  pause
  exit /b 1
)

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
if "%choice%"=="1" start "" "%PYTHON%" -m aivoice_studio.app & exit /b 0
if "%choice%"=="2" goto server
if "%choice%"=="3" goto clean
if "%choice%"=="0" exit /b 0
goto menu

:server
"%PYTHON%" "%ROOT%\scripts\launch.py"
pause >nul
exit /b 0

:clean
echo.
echo   This deletes "%ROOT%\workdir" and "%ROOT%\logs\*.log".
set /p confirm="  Type YES to confirm: "
if /i not "%confirm%"=="YES" echo   Cancelled. & pause & goto menu
if exist "%ROOT%\workdir" rmdir /s /q "%ROOT%\workdir"
if not exist "%ROOT%\workdir" mkdir "%ROOT%\workdir"
if exist "%ROOT%\logs" del /q "%ROOT%\logs\*.log"
echo   Done.
pause
goto menu
