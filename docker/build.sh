#!/bin/bash

# Get the absolute path to the project root directory
PROJECT_ROOT=$(dirname "$(dirname "$(readlink -f "$0")")")
DOCKER_DIR=$(dirname "$(readlink -f "$0")")

echo "Project root: $PROJECT_ROOT"
echo "Docker directory: $DOCKER_DIR"

# Check if function templates exist
if [ ! -d "$PROJECT_ROOT/function_templates" ]; then
    echo "Creating function_templates directory structure..."
    mkdir -p "$PROJECT_ROOT/function_templates/python"
    mkdir -p "$PROJECT_ROOT/function_templates/javascript"
    
    # Create python handler if it doesn't exist
    if [ ! -f "$PROJECT_ROOT/function_templates/python/function_handler.py" ]; then
        echo "Creating Python function handler template..."
        cat > "$PROJECT_ROOT/function_templates/python/function_handler.py" << 'EOF'
import sys
import json
import importlib.util
import traceback
import os
import time
from typing import Dict, Any

def load_function(function_path: str, function_name: str):
    """
    Dynamically load the user function from the specified path.
    """
    spec = importlib.util.spec_from_file_location("user_function", function_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    if not hasattr(module, function_name):
        raise ImportError(f"Function '{function_name}' not found in module")
    
    return getattr(module, function_name)

def handle_request():
    """
    Main handler for incoming function execution requests.
    """
    # Get the execution parameters from environment variables
    function_path = os.environ.get("FUNCTION_PATH", "/function/function_code.py")
    function_name = os.environ.get("FUNCTION_NAME", "handler")
    input_data = os.environ.get("INPUT_DATA", "{}")
    
    # Load the user function
    try:
        user_function = load_function(function_path, function_name)
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to load function: {str(e)}",
            "traceback": traceback.format_exc()
        }
    
    # Execute the function with the provided input
    start_time = time.time()
    try:
        input_obj = json.loads(input_data)
        result = user_function(input_obj)
        execution_time = time.time() - start_time
        
        # Ensure the result is JSON serializable
        try:
            json.dumps(result)
        except TypeError:
            result = str(result)
        
        return {
            "status": "success",
            "result": result,
            "execution_time": execution_time
        }
    except Exception as e:
        execution_time = time.time() - start_time
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "execution_time": execution_time
        }

if __name__ == "__main__":
    response = handle_request()
    # Print response to stdout for the container to capture
    print(json.dumps(response))
EOF
    fi
    
    # Create javascript handler if it doesn't exist
    if [ ! -f "$PROJECT_ROOT/function_templates/javascript/function_handler.js" ]; then
        echo "Creating JavaScript function handler template..."
        cat > "$PROJECT_ROOT/function_templates/javascript/function_handler.js" << 'EOF'
const fs = require('fs');
const path = require('path');

// Get environment variables for execution
const functionPath = process.env.FUNCTION_PATH || '/function/function_code.js';
const functionName = process.env.FUNCTION_NAME || 'handler';
const inputDataStr = process.env.INPUT_DATA || '{}';

/**
 * Load and execute the user function
 */
async function executeFunction() {
  try {
    // Load the user function
    const userModule = require(functionPath);
    
    if (typeof userModule[functionName] !== 'function') {
      throw new Error(`Function '${functionName}' not found in module`);
    }
    
    // Parse input data
    const inputData = JSON.parse(inputDataStr);
    
    // Execute the function
    const startTime = Date.now();
    
    try {
      // Check if function returns a promise
      const fnResult = userModule[functionName](inputData);
      let result;
      
      if (fnResult instanceof Promise) {
        result = await fnResult;
      } else {
        result = fnResult;
      }
      
      const executionTime = (Date.now() - startTime) / 1000;
      
      // Return success result
      return {
        status: 'success',
        result: result,
        execution_time: executionTime
      };
    } catch (execError) {
      const executionTime = (Date.now() - startTime) / 1000;
      
      // Return error result
      return {
        status: 'error',
        error: execError.message,
        traceback: execError.stack,
        execution_time: executionTime
      };
    }
  } catch (loadError) {
    // Return load error result
    return {
      status: 'error',
      error: `Failed to load function: ${loadError.message}`,
      traceback: loadError.stack
    };
  }
}

// Execute the function and print the result
executeFunction()
  .then(result => {
    console.log(JSON.stringify(result));
  })
  .catch(error => {
    console.log(JSON.stringify({
      status: 'error',
      error: `Execution failed: ${error.message}`,
      traceback: error.stack
    }));
  });
EOF
    fi
fi

# Copy the function handlers to the docker directory for the build context
echo "Copying function handlers to Docker build context..."
cp "$PROJECT_ROOT/function_templates/python/function_handler.py" "$DOCKER_DIR/"
cp "$PROJECT_ROOT/function_templates/javascript/function_handler.js" "$DOCKER_DIR/"

# Build the Docker images
echo "Building Python function image..."
docker build -t python-function:latest -f "$DOCKER_DIR/Dockerfile.python" "$DOCKER_DIR"

echo "Building JavaScript function image..."
docker build -t javascript-function:latest -f "$DOCKER_DIR/Dockerfile.javascript" "$DOCKER_DIR"

# Clean up - remove the copied files
rm "$DOCKER_DIR/function_handler.py"
rm "$DOCKER_DIR/function_handler.js"

echo "Function images built successfully"
