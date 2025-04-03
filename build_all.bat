@echo off
echo Building all Docker images for the serverless platform...

cd docker
call build.bat

echo All images built successfully!
echo Running function tests...

cd ..
python tests\test_docker_connection.py

echo Starting the server...
python backend\main.py
