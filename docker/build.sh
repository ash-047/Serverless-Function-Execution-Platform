#!/bin/bash
# Mac OS version of build.bat

# Copy the function handlers to the docker directory for the build context
cp ../function_templates/python/function_handler.py .
cp ../function_templates/javascript/function_handler.js .

# Build the Docker images
echo "Building Python function image..."
docker build -t python-function:latest -f Dockerfile.python .

echo "Building JavaScript function image..."
docker build -t javascript-function:latest -f Dockerfile.javascript .

# Clean up - remove the copied files
rm function_handler.py
rm function_handler.js

echo "Function images built successfully"
