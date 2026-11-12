@echo off
title College Admission Portal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo.
  echo Python environment not found.
  echo Create it with: py -m venv venv
  echo Then install dependencies: venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo ============================================================
echo  College Admission Portal
echo ============================================================
echo  Public site:  http://localhost:5000/
echo  Courses:      http://localhost:5000/courses
echo  Admin login:  http://localhost:5000/admin/login
echo  Admin console:http://localhost:5000/admin-console/
echo.
echo  Keep this window open while you use the site.
echo  Press Ctrl+C to stop the server.
echo ============================================================
echo.

start "" cmd /c "timeout /t 3 >nul & start http://localhost:5000/"
"venv\Scripts\python.exe" wsgi.py

echo.
echo Server stopped.
pause
