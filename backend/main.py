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
async def execute_stored_function(
    function_id: str, 
    input_data: Dict[str, Any] = Body(...),
    runtime: Optional[Runtime] = Query(None)
):
    """Execute a stored function"""
    if function_id not in functions_db:
        raise HTTPException(status_code=404, detail="Function not found")
    
    function = functions_db[function_id]
    try:
        
        selected_runtime = runtime or function.get("preferred_runtime") or Runtime.docker
        
        
        execution_id = f"exec-{function_id}-{int(time.time())}"
        
       
        runtime_engine = None
        if function.get("language") == Language.javascript:
            if selected_runtime == Runtime.gvisor:
                runtime_engine = gvisor_js
            else:
                runtime_engine = docker_js
        else:
            if selected_runtime == Runtime.gvisor:
                runtime_engine = gvisor_py
            else:
                runtime_engine = docker_py
            
        
        result = runtime_engine.execute_function(
            code=function["code"],
            function_name=function["function_name"],
            input_data=input_data,
            timeout=function.get("timeout", 60)
        )
        
        
        result["execution_id"] = execution_id
        
        
        metrics_manager.record_execution({
            "execution_id": execution_id,
            "function_id": function_id,
            "language": function.get("language"),
            "runtime": selected_runtime,
            "status": result.get("status"),
            "execution_time": result.get("execution_time"),
            "warm_start": result.get("warm_start", False),
            "error": result.get("error"),
            "timestamp": time.time()
        })
        
        return result
    except Exception as e:
        
        metrics_manager.record_execution({
            "execution_id": f"error-{function_id}-{int(time.time())}",
            "function_id": function_id,
            "language": function.get("language"),
            "runtime": runtime or function.get("preferred_runtime") or Runtime.docker,
            "status": "error",
            "error": str(e),
            "timestamp": time.time()
        })
        
        raise HTTPException(status_code=500, detail=f"Function execution failed: {str(e)}")

@app.get("/metrics")
async def get_metrics():
    """Get metrics for function executions"""
    return metrics_manager.get_metrics()

@app.get("/metrics/recent")
async def get_recent_executions(limit: int = Query(10, ge=1, le=100)):
    """Get recent function executions"""
    return metrics_manager.get_recent_executions(limit=limit)

@app.get("/metrics/by-runtime")
async def get_metrics_by_runtime():
    """Get metrics aggregated by runtime"""
    metrics = metrics_manager.get_metrics()
    return metrics.get("by_runtime", {})

@app.get("/metrics/by-language")
async def get_metrics_by_language():
    """Get metrics aggregated by language"""
    metrics = metrics_manager.get_metrics()
    return metrics.get("by_language", {})

@app.get("/metrics/hourly")
async def get_hourly_metrics():
    """Get hourly metrics"""
    metrics = metrics_manager.get_metrics()
    return metrics.get("hourly_stats", {})

@app.get("/metrics/function/{function_id}")
async def get_function_metrics(function_id: str):
    """Get metrics for a specific function"""
    criteria = {"function_id": function_id}
    executions = metrics_manager.get_executions_by_criteria(criteria)
    
    if not executions:
        return {
            "total": 0,
            "success": 0,
            "error": 0,
            "avg_time": 0
        }
    
    total = len(executions)
    success = sum(1 for e in executions if e.get("status") == "success")
    error = total - success
    
    
    exec_times = [e.get("execution_time", 0) for e in executions if "execution_time" in e]
    avg_time = sum(exec_times) / len(exec_times) if exec_times else 0
    
  
    latest = max([e.get("timestamp", 0) for e in executions]) if executions else 0
    
    return {
        "total": total,
        "success": success,
        "error": error,
        "avg_time": avg_time,
        "latest_execution": latest
    }

@app.delete("/functions/{function_id}")
async def delete_function(function_id: str):
    """Delete a function"""
    if function_id not in functions_db:
        raise HTTPException(status_code=404, detail="Function not found")
    
    del functions_db[function_id]
    return {"message": f"Function {function_id} deleted successfully"}

@app.get("/system/info", dependencies=[Depends(get_api_key)])
async def get_system_info():
    """Get system information (protected endpoint)"""
    
    pool_metrics = {}
    
    if hasattr(docker_py, 'container_pool') and docker_py.container_pool:
        pool_metrics["docker_python"] = docker_py.container_pool.get_pool_metrics()
        
    if hasattr(docker_js, 'container_pool') and docker_js.container_pool:
        pool_metrics["docker_javascript"] = docker_js.container_pool.get_pool_metrics()
    
    return {
        "runtimes": {
            "docker": {"available": True},
            "gvisor": {"available": gvisor_available}
        },
        "container_pools": pool_metrics,
        "metrics_storage": os.path.exists(metrics_dir),
        "stored_functions": len(functions_db)
    }

@app.get("/system/status")
async def get_system_status():
    """Get detailed system status"""
    
    pool_metrics = {}
    
    if hasattr(docker_py, 'container_pool') and docker_py.container_pool:
        pool_metrics["docker_python"] = docker_py.container_pool.get_pool_metrics()
        
    if hasattr(docker_js, 'container_pool') and docker_js.container_pool:
        pool_metrics["docker_javascript"] = docker_js.container_pool.get_pool_metrics()
    
    metrics = metrics_manager.get_metrics()
    
    try:
        active_containers = len(docker_py.client.containers.list())
    except:
        active_containers = 0
    
    functions_by_language = {
        "python": sum(1 for f in functions_db.values() if f.get("language") == "python"),
        "javascript": sum(1 for f in functions_db.values() if f.get("language") == "javascript")
    }
    
    return {
        "uptime": time.time() - startup_time,
        "active_containers": active_containers,
        "stored_functions": len(functions_db),
        "functions_by_language": functions_by_language,
        "execution_count": metrics.get("total_executions", 0),
        "success_rate": (metrics.get("successful_executions", 0) / metrics.get("total_executions", 1)) * 100 if metrics.get("total_executions", 0) > 0 else 0,
        "container_pools": pool_metrics,
        "runtimes": {
            "docker": {"available": True},
            "gvisor": {"available": gvisor_available}
        }
    }


startup_time = time.time()

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    
    docker_py.preload_image()
    docker_js.preload_image()

@app.on_event("shutdown")
def shutdown_event():
    """Clean up resources when shutting down"""
    docker_py.shutdown()
    docker_js.shutdown()

def preload_image(self) -> None:
    """
    Ensure the base image is available locally.
    If not, it will be built from the Dockerfile.
    """
    try:
        self.client.images.get(self.base_image)
        print(f"Image {self.base_image} is already available")
    except docker.errors.ImageNotFound:
        print(f"Image {self.base_image} not found locally. Building...")
        
        build_path = os.path.join(os.getcwd(), "docker")
        
        dockerfile = "Dockerfile.python"
        if self.language == "javascript":
            dockerfile = "Dockerfile.javascript"
            
        if platform.system() == "Darwin":
            handler_file = "function_handler.py" if self.language == "python" else "function_handler.js"
            template_path = os.path.join(os.getcwd(), "function_templates", self.language, handler_file)
            docker_path = os.path.join(build_path, handler_file)
            
            if os.path.exists(template_path) and not os.path.exists(docker_path):
                import shutil
                shutil.copy(template_path, docker_path)
            
        self.client.images.build(
            path=build_path,
            dockerfile=dockerfile,
            tag=self.base_image
        )
        print(f"Image {self.base_image} built successfully")
        
        if platform.system() == "Darwin":
            if os.path.exists(docker_path):
                os.remove(docker_path)

if __name__ == "__main__":
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
