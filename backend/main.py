import os
import json
import platform
import sys
import traceback
from enum import Enum
from fastapi import FastAPI, HTTPException, Body, Query, Security, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import uvicorn
import time
import hashlib
import secrets
import docker

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

print("Importing execution engines...")
from execution_engine.runtime_factory import RuntimeFactory
from metrics.metrics_manager import MetricsManager

app = FastAPI(title="Serverless Function Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
    print(f"Created static directory: {static_dir}")

app.mount("/static", StaticFiles(directory=static_dir), name="static")

metrics_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metrics_data")
if not os.path.exists(metrics_dir):
    os.makedirs(metrics_dir)
    print(f"Created metrics directory: {metrics_dir}")

metrics_manager = MetricsManager(storage_dir=metrics_dir)

gvisor_available = RuntimeFactory.is_gvisor_available()
print(f"gVisor runtime {'is' if gvisor_available else 'is not'} available")

print("Initializing execution engines...")
docker_py = RuntimeFactory.create_runtime("docker", "python", use_pool=True)
docker_js = RuntimeFactory.create_runtime("docker", "javascript", use_pool=True)

gvisor_py = RuntimeFactory.create_runtime("gvisor", "python", use_pool=False)
gvisor_js = RuntimeFactory.create_runtime("gvisor", "javascript", use_pool=False)

print("Execution engines initialized successfully!")

class Language(str, Enum):
    python = "python"
    javascript = "javascript"

class Runtime(str, Enum):
    docker = "docker"
    gvisor = "gvisor"

class FunctionExecutionRequest(BaseModel):
    code: str
    function_name: str = "handler"
    input_data: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = None
    language: Language = Language.python
    runtime: Runtime = Runtime.docker

class FunctionCreateRequest(BaseModel):
    name: str
    code: str
    function_name: str = "handler"
    description: Optional[str] = None
    language: Language = Language.python
    timeout: Optional[int] = 60
    memory: Optional[int] = 128  

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

functions_db = {}

API_KEY = "serverless-platform-demo-key"
API_KEY_NAME = "X-API-Key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header == API_KEY:
        return api_key_header
    return None

@app.get("/")
async def root():
    """Serve the main UI page with a documentation link"""
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/docs/guide")
async def documentation():
    """Serve the documentation page"""
    return FileResponse(os.path.join(static_dir, "docs.html"))

@app.post("/execute")
async def execute_function(request: FunctionExecutionRequest):
    """Execute a function directly from the request"""
    try:
        
        print(f"Executing {request.language} function: {request.function_name} with {request.runtime} runtime")
        print(f"Input data: {request.input_data}")
        
        runtime = None
        if request.language == Language.javascript:
            if request.runtime == Runtime.gvisor:
                runtime = gvisor_js
            else:
                runtime = docker_js
        else:
            if request.runtime == Runtime.gvisor:
                runtime = gvisor_py
            else:
                runtime = docker_py
            
        execution_id = f"exec-{int(time.time())}-{hashlib.md5(request.code.encode()).hexdigest()[:6]}"
        
        result = runtime.execute_function(
            code=request.code,
            function_name=request.function_name,
            input_data=request.input_data,
            timeout=request.timeout
        )
        
        result["execution_id"] = execution_id
        
        metrics_manager.record_execution({
            "execution_id": execution_id,
            "language": request.language,
            "runtime": request.runtime,
            "status": result.get("status"),
            "execution_time": result.get("execution_time"),
            "warm_start": result.get("warm_start", False),
            "error": result.get("error"),
            "timestamp": time.time()
        })
        
        print(f"Execution result: {result.get('status', 'unknown')}")
        return result
    except Exception as e:
        print(f"Error executing function: {str(e)}")
        print(traceback.format_exc())
        
        metrics_manager.record_execution({
            "execution_id": f"error-{int(time.time())}",
            "language": request.language,
            "runtime": request.runtime,
            "status": "error",
            "error": str(e),
            "timestamp": time.time()
        })
        
        raise HTTPException(status_code=500, detail=f"Function execution failed: {str(e)}")

@app.post("/functions")
async def create_function(request: FunctionCreateRequest):
    """Create/update a stored function"""
    function_id = request.name.lower().replace(" ", "-")
    
    now = time.time()
    
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