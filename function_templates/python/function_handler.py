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
