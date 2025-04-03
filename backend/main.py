import os
import json
import platform
import sys
import traceback
from enum import Enum
from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import uvicorn
import time

# Print diagnostic information to help with debugging
def print_diagnostic_info():
    print("=== Diagnostic Information ===")
    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"System: {platform.system()}")
    if platform.system() == "Linux":
        print(f"Linux release: {platform.uname().release}")
        print(f"WSL detected: {'microsoft' in platform.uname().release.lower()}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Docker socket exists: {os.path.exists('/var/run/docker.sock')}")
    print("============================")

print_diagnostic_info()

# Import our execution engine
print("Importing Docker runtime...")
from execution_engine.docker_runtime import DockerRuntime

app = FastAPI(title="Serverless Function Platform")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define the static files directory (relative to where the app is run)
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
    print(f"Created static directory: {static_dir}")

# Mount the static files directory
app.mount("/static", StaticFiles(directory=static_dir), name="static")

print("Initializing Docker runtime...")
# Initialize Python and JavaScript runtimes
runtime_py = DockerRuntime(base_image="python-function:latest", use_pool=False, language="python")
runtime_js = DockerRuntime(base_image="javascript-function:latest", use_pool=False, language="javascript")
print("Docker runtimes initialized successfully!")

# Define language enum
class Language(str, Enum):
    python = "python"
    javascript = "javascript"

# Models for request/response
class FunctionExecutionRequest(BaseModel):
    code: str
    function_name: str = "handler"
    input_data: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = None
    language: Language = Language.python

class FunctionCreateRequest(BaseModel):
    name: str
    code: str
    function_name: str = "handler"
    description: Optional[str] = None
    language: Language = Language.python
    timeout: Optional[int] = 60
    memory: Optional[int] = 128  # Memory limit in MB

class FunctionMetadata(BaseModel):
    id: str
    name: str
    function_name: str
    description: Optional[str] = None
    language: Language
    timeout: int = 60
    memory: int = 128
    created_at: Optional[float] = None
    updated_at: Optional[float] = None

# Simple in-memory storage for functions
functions_db = {}

@app.get("/")
async def root():
    """Serve the main UI page"""
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.post("/execute")
async def execute_function(request: FunctionExecutionRequest):
    """Execute a function directly from the request"""
    try:
        # Add more detailed logging
        print(f"Executing {request.language} function: {request.function_name}")
        print(f"Input data: {request.input_data}")
        
        # Select the appropriate runtime based on language
        if request.language == Language.javascript:
            runtime = runtime_js
        else:
            runtime = runtime_py
            
        result = runtime.execute_function(
            code=request.code,
            function_name=request.function_name,
            input_data=request.input_data,
            timeout=request.timeout
        )
        
        print(f"Execution result: {result.get('status', 'unknown')}")
        return result
    except Exception as e:
        print(f"Error executing function: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Function execution failed: {str(e)}")

@app.post("/functions")
async def create_function(request: FunctionCreateRequest):
    """Create/update a stored function"""
    function_id = request.name.lower().replace(" ", "-")
    
    # Add timestamp for creation/update
    now = time.time()
    
    # Check if updating or creating
    is_update = function_id in functions_db
    
    functions_db[function_id] = {
        "id": function_id,
        "name": request.name,
        "code": request.code,
        "function_name": request.function_name,
        "description": request.description,
        "language": request.language,
        "timeout": request.timeout or 60,
        "memory": request.memory or 128,
        "created_at": functions_db.get(function_id, {}).get("created_at", now),
        "updated_at": now
    }
    
    message = "updated" if is_update else "created"
    return {"id": function_id, "message": f"Function {message} successfully"}

@app.get("/functions")
async def list_functions():
    """List all stored functions"""
    return list(functions_db.values())

@app.get("/functions/{function_id}")
async def get_function(function_id: str):
    """Get a specific function"""
    if function_id not in functions_db:
        raise HTTPException(status_code=404, detail="Function not found")
    return functions_db[function_id]

@app.post("/functions/{function_id}/execute")
async def execute_stored_function(function_id: str, input_data: Dict[str, Any] = Body(...)):
    """Execute a stored function"""
    if function_id not in functions_db:
        raise HTTPException(status_code=404, detail="Function not found")
    
    function = functions_db[function_id]
    try:
        # Select the appropriate runtime based on function language
        if function.get("language") == Language.javascript:
            runtime = runtime_js
        else:
            runtime = runtime_py
            
        result = runtime.execute_function(
            code=function["code"],
            function_name=function["function_name"],
            input_data=input_data,
            timeout=function.get("timeout", 60)
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Function execution failed: {str(e)}")

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    # Build the Docker images if they don't exist
    runtime_py.preload_image()
    runtime_js.preload_image()

@app.on_event("shutdown")
def shutdown_event():
    """Clean up resources when shutting down"""
    runtime_py.shutdown()
    runtime_js.shutdown()

if __name__ == "__main__":
    # Start the API server
    uvicorn.run(app, host="0.0.0.0", port=8000)
