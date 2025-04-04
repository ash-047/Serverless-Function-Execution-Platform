#!/bin/bash
# Mac OS version of run_server_debug.bat

echo "Starting serverless function platform in debug mode..."

# Set environment variables for detailed logging
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=UTF-8
export LOG_LEVEL=DEBUG

# Make sure the Docker image exists
cd docker
bash build.sh
cd ..

# Start the server
python3 backend/main.py
