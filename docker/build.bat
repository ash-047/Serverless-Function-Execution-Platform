@echo off
REM 
copy ..\function_templates\python\function_handler.py .
copy ..\function_templates\javascript\function_handler.js .

REM 
echo Building Python function image...
docker build -t python-function:latest -f Dockerfile.python .

echo Building JavaScript function image...
docker build -t javascript-function:latest -f Dockerfile.javascript .

REM
del function_handler.py
del function_handler.js

echo Function images built successfully
