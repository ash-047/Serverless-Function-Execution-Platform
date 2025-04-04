import requests
import json
import time

SIMPLE_FUNCTION = """
def handler(event):
    name = event.get('name', 'World')
    return {
        "message": f"Hello, {name}!"
    }
"""

def test_api():
    """Test the function execution API with a simple function"""
    print("Testing direct function execution via API...")
    
    response = requests.post(
        "http://localhost:8000/execute",
        json={
            "code": SIMPLE_FUNCTION,
            "input_data": {"name": "Serverless"}
        }
    )
    
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"Response: {json.dumps(result, indent=2)}")
        if result.get("status") == "success":
            print("✅ Test passed!")
        else:
            print("❌ Test failed!")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    print("Waiting for server to be ready...")
    time.sleep(2)
    test_api()
