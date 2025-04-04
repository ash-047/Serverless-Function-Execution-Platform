import sys
import os
import json
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.execution_engine.docker_runtime import DockerRuntime

FIBONACCI_FUNCTION = """
def handler(event):
    n = event.get("n", 10)
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    return {
        "input": n,
        "result": fib,
        "length": len(fib)
    }
"""

SIMPLE_ADDITION = """
def handler(event):
    a = event.get("a", 0)
    b = event.get("b", 0)
    return {"result": a + b}
"""

def test_direct_execution():
    """Test executing functions directly with the DockerRuntime"""
    print("\n=== Testing direct execution with DockerRuntime ===")
    
    # Initialize the runtime
    runtime = DockerRuntime(base_image="python-function:latest", use_pool=False)
    
    # Make sure the image is available
    runtime.preload_image()
    
    # Test Fibonacci function
    print("\nTesting Fibonacci function...")
    result = runtime.execute_function(
        code=FIBONACCI_FUNCTION,
        function_name="handler",
        input_data={"n": 10}
    )
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Test addition function
    print("\nTesting Addition function...")
    result = runtime.execute_function(
        code=SIMPLE_ADDITION,
        function_name="handler",
        input_data={"a": 5, "b": 7}
    )
    print(f"Result: {json.dumps(result, indent=2)}")
    
    # Clean up
    runtime.shutdown()

def test_api_execution(base_url="http://localhost:8000"):
    """Test executing functions via the API"""
    print("\n=== Testing execution via API ===")
    
    # Test direct execution endpoint
    print("\nTesting /execute endpoint...")
    response = requests.post(
        f"{base_url}/execute",
        json={
            "code": FIBONACCI_FUNCTION,
            "function_name": "handler",
            "input_data": {"n": 12}
        }
    )
    
    if response.status_code == 200:
        print(f"API Response: {json.dumps(response.json(), indent=2)}")
    else:
        print(f"API Error: {response.status_code} - {response.text}")
    
    # Test function storage and execution
    print("\nTesting function storage and execution...")
    
    # Create a function
    create_response = requests.post(
        f"{base_url}/functions",
        json={
            "name": "Addition Function",
            "code": SIMPLE_ADDITION,
            "function_name": "handler",
            "description": "Simple function that adds two numbers"
        }
    )
    
    if create_response.status_code == 200:
        function_id = create_response.json()["id"]
        print(f"Created function with ID: {function_id}")
        
        # Execute the stored function
        exec_response = requests.post(
            f"{base_url}/functions/{function_id}/execute",
            json={"a": 10, "b": 20}
        )
        
        if exec_response.status_code == 200:
            print(f"Execution result: {json.dumps(exec_response.json(), indent=2)}")
        else:
            print(f"Execution error: {exec_response.status_code} - {exec_response.text}")
    else:
        print(f"Creation error: {create_response.status_code} - {create_response.text}")

if __name__ == "__main__":
    try:
        test_direct_execution()
    except Exception as e:
        print(f"Direct execution test failed: {str(e)}")
    
    # Test API execution (only if server is running)
    try:
        # Check if API server is running
        try:
            requests.get("http://localhost:8000")
            test_api_execution()
        except requests.exceptions.ConnectionError:
            print("\nAPI server is not running. Skipping API tests.")
            print("Start the server with: python backend/main.py")
    except Exception as e:
        print(f"API execution test failed: {str(e)}")
