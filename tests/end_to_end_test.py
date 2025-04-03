import requests
import json
import time
import random
import sys
import os

# Base URL for the API
API_URL = "http://localhost:8000"

# Sample functions
PYTHON_FUNCTION = """
def handler(event):
    name = event.get('name', 'World')
    return {
        "message": f"Hello, {name}!",
        "timestamp": event.get('timestamp', 0)
    }
"""

JS_FUNCTION = """
function handler(event) {
    const name = event.name || 'World';
    return {
        message: `Hello, ${name}!`,
        timestamp: event.timestamp || 0
    };
}

module.exports = { handler };
"""

def print_header(title):
    """Print a section header"""
    print("\n" + "="*80)
    print(f" {title}")
    print("="*80)

def test_api_connectivity():
    """Test basic API connectivity"""
    print_header("Testing API Connectivity")
    
    try:
        response = requests.get(f"{API_URL}/")
        if response.status_code == 200:
            print("✅ Connected to API server")
            return True
        else:
            print(f"❌ Failed to connect to API server: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error connecting to API server: {e}")
        return False

def test_function_execution(language="python"):
    """Test direct function execution"""
    print_header(f"Testing {language.capitalize()} Function Execution")
    
    code = PYTHON_FUNCTION if language == "python" else JS_FUNCTION
    timestamp = int(time.time())
    
    try:
        response = requests.post(
            f"{API_URL}/execute",
            json={
                "code": code,
                "language": language,
                "runtime": "docker",
                "input_data": {"name": "E2E Test", "timestamp": timestamp}
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Function executed successfully")
            print(f"Result: {json.dumps(result, indent=2)}")
            
            # Verify the result contains the expected data
            if result.get("status") != "success":
                print(f"❌ Execution status not successful: {result.get('status')}")
                return False
                
            if language == "python" and result.get("result", {}).get("message") != "Hello, E2E Test!":
                print(f"❌ Unexpected result message: {result.get('result', {}).get('message')}")
                return False
                
            print("✅ Result validation passed")
            return True
        else:
            print(f"❌ Function execution failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error during function execution: {e}")
        return False

def test_function_management():
    """Test function management (create, get, list, execute, delete)"""
    print_header("Testing Function Management")
    
    function_name = f"TestFunction_{random.randint(1000, 9999)}"
    function_id = None
    
    # Create function
    try:
        response = requests.post(
            f"{API_URL}/functions",
            json={
                "name": function_name,
                "code": PYTHON_FUNCTION,
                "description": "Test function created by E2E test",
                "language": "python"
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            function_id = result.get("id")
            print(f"✅ Function created with ID: {function_id}")
        else:
            print(f"❌ Function creation failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error creating function: {e}")
        return False
    
    # Get function
    try:
        response = requests.get(f"{API_URL}/functions/{function_id}")
        
        if response.status_code == 200:
            function = response.json()
            print(f"✅ Retrieved function: {function.get('name')}")
            
            if function.get("name") != function_name:
                print(f"❌ Function name mismatch: {function.get('name')} != {function_name}")
                return False
        else:
            print(f"❌ Function retrieval failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error retrieving function: {e}")
        return False
    
    # List functions
    try:
        response = requests.get(f"{API_URL}/functions")
        
        if response.status_code == 200:
            functions = response.json()
            print(f"✅ Listed {len(functions)} functions")
            
            # Check if our function is in the list
            found = any(func.get("id") == function_id for func in functions)
            if not found:
                print(f"❌ Function {function_id} not found in function list")
                return False
        else:
            print(f"❌ Function listing failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error listing functions: {e}")
        return False
    
    # Execute function
    try:
        response = requests.post(
            f"{API_URL}/functions/{function_id}/execute",
            json={"name": "E2E Test"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Function executed successfully")
            
            if result.get("status") != "success":
                print(f"❌ Execution status not successful: {result.get('status')}")
                return False
                
            if result.get("result", {}).get("message") != "Hello, E2E Test!":
                print(f"❌ Unexpected result message: {result.get('result', {}).get('message')}")
                return False
        else:
            print(f"❌ Function execution failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error executing function: {e}")
        return False
    
    # Delete function
    try:
        response = requests.delete(f"{API_URL}/functions/{function_id}")
        
        if response.status_code == 200:
            print(f"✅ Function deleted successfully")
        else:
            print(f"❌ Function deletion failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error deleting function: {e}")
        return False
    
    # Verify function is gone
    try:
        response = requests.get(f"{API_URL}/functions/{function_id}")
        
        if response.status_code == 404:
            print(f"✅ Function confirmed deleted")
        else:
            print(f"❌ Function still exists after deletion: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error checking function deletion: {e}")
        return False
    
    return True

def test_metrics():
    """Test metrics endpoints"""
    print_header("Testing Metrics")
    
    endpoints = [
        "/metrics",
        "/metrics/recent",
        "/metrics/by-runtime",
        "/metrics/by-language",
        "/system/status"
    ]
    
    success = True
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{API_URL}{endpoint}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ {endpoint} returned data successfully")
            else:
                print(f"❌ {endpoint} failed: {response.status_code} - {response.text}")
                success = False
        except Exception as e:
            print(f"❌ Error accessing {endpoint}: {e}")
            success = False
    
    return success

def run_all_tests():
    """Run all E2E tests"""
    print_header("Starting End-to-End Tests")
    
    # Track test results
    results = {}
    
    # Test 1: API Connectivity
    results["api_connectivity"] = test_api_connectivity()
    
    if not results["api_connectivity"]:
        print("❌ API connectivity test failed, aborting remaining tests")
        return results
    
    # Test 2: Python Function Execution
    results["python_execution"] = test_function_execution("python")
    
    # Test 3: JavaScript Function Execution
    results["javascript_execution"] = test_function_execution("javascript")
    
    # Test 4: Function Management
    results["function_management"] = test_function_management()
    
    # Test 5: Metrics
    results["metrics"] = test_metrics()
    
    # Print summary
    print_header("Test Summary")
    for test, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test}")
    
    return results

if __name__ == "__main__":
    # Check if the API server is running
    try:
        requests.get(f"{API_URL}/")
    except requests.exceptions.ConnectionError:
        print(f"❌ API server is not running at {API_URL}")
        print("Start the server with: python backend/main.py")
        sys.exit(1)
    
    # Run all tests
    results = run_all_tests()
    
    # Exit with appropriate status code
    if all(results.values()):
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)
