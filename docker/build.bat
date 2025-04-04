@echo off
REM Copy the function handlers to the docker directory for the build context
copy ..\function_templates\python\function_handler.py .
copy ..\function_templates\javascript\function_handler.js .

REM Build the Docker images
echo Building Python function image...
docker build -t python-function:latest -f Dockerfile.python .

echo Building JavaScript function image...
docker build -t javascript-function:latest -f Dockerfile.javascript .

REM Clean up - remove the copied files
del function_handler.py
del function_handler.js

echo Function images built successfully
