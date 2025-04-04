#!/bin/bash
# Mac OS version of build_all.bat

echo "Building all Docker images for the serverless platform..."

cd docker
bash build.sh

echo "All images built successfully!"
echo "Running function tests..."

cd ..
python3 tests/test_docker_connection.py

echo "Starting the server..."
python3 backend/main.py
