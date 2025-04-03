@echo off
echo Starting serverless function platform in debug mode...

REM Set environment variables for detailed logging
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=UTF-8
set LOG_LEVEL=DEBUG

REM Make sure the Docker image exists
cd docker
call build.bat
cd ..

REM Start the server
python backend\main.py
