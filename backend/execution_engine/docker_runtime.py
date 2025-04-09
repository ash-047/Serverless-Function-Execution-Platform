import docker
import json
import os
import tempfile
import time
import uuid
from typing import Dict, Any, Optional, Tuple
import platform
import traceback
from .container_pool import ContainerPool

class DockerRuntime:
    def __init__(self, base_image="python-function:latest", timeout=60, use_pool=True, language="python"):
        try:
            if platform.system() == "Windows":
                self.client = docker.DockerClient(base_url='npipe:////./pipe/docker_engine')
                print("Using Windows named pipe for Docker connection")
            elif platform.system() == "Darwin":  
                self.client = docker.from_env()
                print("Using default Docker connection on macOS")
            else:
                self.client = docker.from_env()
                print("Using default Docker connection")
                
            self.client.ping()
            print("Successfully connected to Docker daemon")
        except Exception as e:
            print(f"Error connecting to Docker: {e}")
            raise
        
        self.language = language.lower()
        if self.language == "javascript":
            self.base_image = "javascript-function:latest"
            self.file_extension = ".js"
            print(f"Using JavaScript runtime with {self.base_image}")
        else:
            self.base_image = base_image
            self.file_extension = ".py"
            print(f"Using Python runtime with {self.base_image}")
            
        self.default_timeout = timeout
        self.use_pool = use_pool
        
        if self.use_pool:
            print("Initializing container pool")
            self.container_pool = ContainerPool(base_image=self.base_image)
        else:
            print("Container pool disabled")
            self.container_pool = None

    def _prepare_function_code(self, code: str) -> Tuple[str, str]:
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, f"function_code{self.file_extension}")
        with open(file_path, "w") as f:
            f.write(code)
        return file_path, temp_dir

    def execute_function(self, 
                    code: str, 
                    function_name: str = "handler", 
                    input_data: Dict[str, Any] = None, 
                    timeout: Optional[int] = None,
                    language: Optional[str] = None,
                    runtime: Optional[str] = None) -> Dict[str, Any]:
        if input_data is None:
            input_data = {}
        if timeout is None:
            timeout = self.default_timeout
        if language and language.lower() != self.language:
            temp_runtime = DockerRuntime(timeout=timeout, use_pool=False, language=language)
            return temp_runtime.execute_function(code, function_name, input_data, timeout)
            
        # Generate execution ID and prepare code
        execution_id = f"exec-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        code_path, temp_dir = self._prepare_function_code(code)
        using_pooled_container = False
        container_id = None
        container = None
        
        try:
            print(f"Starting execution of {self.language} function: {function_name}")
            start_time = time.time()
            
            # Skip pool for gVisor runtime - we'll create a new container with the runtime
            if runtime == "runsc":
                print(f"Using gVisor runtime - skipping container pool")
                using_pooled_container = False
            # Try to get container from pool if enabled
            elif self.use_pool and self.container_pool:
                container_id = self.container_pool.get_container()
                if container_id:
                    using_pooled_container = True
                    print(f"Using pooled container: {container_id[:12]}")
            
            # If we got a container from the pool
            if using_pooled_container:
                try:
                    container = self.client.containers.get(container_id)
                    
                    # Copy function code to container
                    dest_path = f"/function/function_code{self.file_extension}"
                    copy_success = self.container_pool.copy_to_container(container_id, code_path, dest_path)
                    
                    if not copy_success:
                        print("Failed to copy code to container, falling back to new container")
                        using_pooled_container = False
                    else:
                        # Execute the function in the container
                        cmd = ["node", "/function/function_handler.js"] if self.language == "javascript" else ["python", "/function/function_handler.py"]
                        env = {
                            "FUNCTION_PATH": dest_path,
                            "FUNCTION_NAME": function_name,
                            "INPUT_DATA": json.dumps(input_data)
                        }
                        
                        # Execute command in container
                        exec_id = self.client.api.exec_create(
                            container=container_id,
                            cmd=cmd,
                            environment=env
                        )
                        
                        # Start the execution and get output
                        exec_output = self.client.api.exec_start(exec_id['Id'])
                        exec_info = self.client.api.exec_inspect(exec_id['Id'])
                        logs = exec_output.decode('utf-8').strip()
                        
                        print(f"Execution completed with exit code: {exec_info.get('ExitCode')}")
                except Exception as e:
                    print(f"Error using pooled container: {e}")
                    print(traceback.format_exc())
                    using_pooled_container = False
            
            # Create a new container if we couldn't use the pool
            if not using_pooled_container:
                container_name = f"function-{execution_id}"
                print(f"Creating new container: {container_name}")
                
                # Prepare container configuration
                container_options = {
                    "image": self.base_image,
                    "detach": True,
                    "name": container_name,
                    "volumes": {
                        code_path: {
                            "bind": f"/function/function_code{self.file_extension}",
                            "mode": "ro"
                        }
                    },
                    "environment": {
                        "FUNCTION_PATH": f"/function/function_code{self.file_extension}",
                        "FUNCTION_NAME": function_name,
                        "INPUT_DATA": json.dumps(input_data)
                    },
                    "mem_limit": "128m",
                    "cpu_quota": 100000,
                    "network_mode": "none"
                }
                
                # Add gVisor runtime if specified
                if runtime:
                    print(f"Using {runtime} runtime for container")
                    container_options["runtime"] = runtime

                # Create and start the container
                container = self.client.containers.run(**container_options)
                container_id = container.id
                print(f"Created container with ID: {container_id[:12]}")
                
                # Wait for execution to complete
                print(f"Waiting for container {container_id[:12]} to complete")
                result = container.wait(timeout=timeout)
                exit_code = result.get("StatusCode", -1)
                logs = container.logs().decode("utf-8").strip()
                print(f"Container completed with exit code: {exit_code}")

            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Parse the output
            try:
                result = json.loads(logs)
                result["execution_time"] = execution_time
                result["container_id"] = container_id
                result["warm_start"] = using_pooled_container
                result["runtime"] = runtime if runtime else "standard"
                
                # Return container to pool if we used one
                if using_pooled_container and self.container_pool:
                    self.container_pool.release_container(container_id, result)
                
                return result
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON output: {e}")
                error_result = {
                    "status": "error",
                    "error": "Failed to parse function output",
                    "logs": logs,
                    "execution_time": execution_time,
                    "warm_start": using_pooled_container,
                    "runtime": runtime if runtime else "standard"
                }
                
                # Return container to pool if we used one
                if using_pooled_container and self.container_pool:
                    self.container_pool.release_container(container_id, error_result)
                    
                return error_result
                
        except Exception as e:
            print(f"Error executing function: {e}")
            print(traceback.format_exc())
            execution_time = time.time() - start_time
            
            error_result = {
                "status": "error",
                "error": f"Function execution failed: {str(e)}",
                "execution_time": execution_time,
                "warm_start": using_pooled_container,
                "runtime": runtime if runtime else "standard"
            }
            
            # Return container to pool if we used one
            if using_pooled_container and container_id and self.container_pool:
                self.container_pool.release_container(container_id, error_result)
                
            return error_result
                
        finally:
            # Clean up resources
            if not using_pooled_container and container_id:
                try:
                    print(f"Cleaning up container: {container_id[:12]}")
                    if container:
                        container.remove(force=True)
                except Exception as e:
                    print(f"Error removing container: {e}")
            
            # Always clean up temp files
            try:
                os.remove(code_path)
                os.rmdir(temp_dir)
            except Exception as e:
                print(f"Error removing temp files: {e}")
    
    def preload_image(self) -> None:
        try:
            self.client.images.get(self.base_image)
            print(f"Image {self.base_image} is already available")
        except docker.errors.ImageNotFound:
            print(f"Image {self.base_image} not found locally. Building...")
            build_path = os.path.join(os.getcwd(), "docker")
            dockerfile = "Dockerfile.python"
            if self.language == "javascript":
                dockerfile = "Dockerfile.javascript"
                
            # For macOS, copy template files to docker directory
            if platform.system() == "Darwin":
                handler_file = "function_handler.py" if self.language == "python" else "function_handler.js"
                template_path = os.path.join(os.getcwd(), "function_templates", self.language, handler_file)
                docker_path = os.path.join(build_path, handler_file)
                if os.path.exists(template_path) and not os.path.exists(docker_path):
                    import shutil
                    shutil.copy(template_path, docker_path)
                
            # Build the image
            self.client.images.build(
                path=build_path,
                dockerfile=dockerfile,
                tag=self.base_image
            )
            print(f"Image {self.base_image} built successfully")
            
            # Clean up copied files on macOS
            if platform.system() == "Darwin":
                if os.path.exists(docker_path):
                    os.remove(docker_path)
    
    def shutdown(self):
        if self.container_pool:
            self.container_pool.shutdown()