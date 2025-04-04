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
        """
        Initialize the Docker runtime for executing functions.
        
        Args:
            base_image: The Docker image to use for function execution
            timeout: Default timeout for function execution in seconds
            use_pool: Whether to use the container pool for warm starts
            language: The programming language ("python" or "javascript")
        """
        # Initialize Docker client for Windows
        try:
            # On Windows, use the named pipe
            if platform.system() == "Windows":
                self.client = docker.DockerClient(base_url='npipe:////./pipe/docker_engine')
                print("Using Windows named pipe for Docker connection")
            else:
                self.client = docker.from_env()
                print("Using default Docker connection")
                
            # Test the connection
            self.client.ping()
            print("Successfully connected to Docker daemon")
        except Exception as e:
            print(f"Error connecting to Docker: {e}")
            raise
        
        # Set language-specific properties
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
        
        # Initialize container pool if warm starts are enabled
        if self.use_pool:
            print("Initializing container pool")
            self.container_pool = ContainerPool(base_image=self.base_image)
        else:
            print("Container pool disabled")
            self.container_pool = None

    def _prepare_function_code(self, code: str) -> Tuple[str, str]:
        """
        Create a temporary file for the function code.
        
        Args:
            code: The function code as a string
            
        Returns:
            The path to the temporary file and the temp directory
        """
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
                        language: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a function in a Docker container.
        
        Args:
            code: The function code as a string
            function_name: The name of the function to execute
            input_data: Input data to pass to the function
            timeout: Timeout for this specific execution (overrides default)
            language: The programming language to use (overrides instance default)
            
        Returns:
            A dictionary containing the execution result or error
        """
        if input_data is None:
            input_data = {}
            
        if timeout is None:
            timeout = self.default_timeout
        
        # Override language if specified
        if language and language.lower() != self.language:
            # Create a new runtime with the specified language
            temp_runtime = DockerRuntime(timeout=timeout, use_pool=False, language=language)
            return temp_runtime.execute_function(code, function_name, input_data, timeout)
            
        # Create a temporary file with the function code
        code_path, temp_dir = self._prepare_function_code(code)
        
        # Track if we're using a pooled container
        using_pooled_container = False
        container_id = None
        container = None
        
        try:
            print(f"Starting execution of {self.language} function: {function_name}")
            # Start execution timestamp
            start_time = time.time()
            
            # Try to get a container from the pool if enabled
            if self.use_pool and self.container_pool:
                container_id = self.container_pool.get_container()
                if container_id:
                    using_pooled_container = True
                    try:
                        container = self.client.containers.get(container_id)
                        # Ensure container is running
                        if container.status != "running":
                            print(f"Container {container_id[:12]} is not running, starting it")
                            container.start()
                            time.sleep(1)  # Give it a moment to start
                    except Exception as e:
                        print(f"Error getting container from pool: {e}")
                        using_pooled_container = False
                        container_id = None
            
            # If no pooled container is available, create a new one
            if not using_pooled_container:
                # Generate a unique container name
                container_name = f"function-{uuid.uuid4()}"
                print(f"Creating new container: {container_name}")
                
                try:
                    # Execute the function in a container
                    container = self.client.containers.run(
                        self.base_image,
                        detach=True,
                        name=container_name,
                        volumes={
                            code_path: {
                                "bind": f"/function/function_code{self.file_extension}",
                                "mode": "ro"
                            }
                        },
                        environment={
                            "FUNCTION_PATH": f"/function/function_code{self.file_extension}",
                            "FUNCTION_NAME": function_name,
                            "INPUT_DATA": json.dumps(input_data)
                        },
                        mem_limit="128m",  # Memory limit
                        cpu_quota=100000,  # 10% of CPU
                        network_mode="none"  # No network access for security
                    )
                    container_id = container.id
                    print(f"Created container with ID: {container_id[:12]}")
                except Exception as e:
                    print(f"Error creating container: {e}")
                    print(traceback.format_exc())
                    raise
            else:
                # Using a pooled container - copy the function code and execute it
                print(f"Using pooled container: {container_id[:12]}")
                try:
                    # Copy the function code to the container
                    with open(code_path, 'rb') as src_file:
                        data = src_file.read()
                        self.client.api.put_archive(container_id, '/function', data)
                    
                    # Create an exec command in the running container
                    print(f"Creating exec command in container: {container_id[:12]}")
                    exec_cmd = self.client.api.exec_create(
                        container=container_id,
                        cmd=["node", "/function/function_handler.js"] if self.language == "javascript" else ["python", "/function/function_handler.py"],
                        environment={
                            "FUNCTION_PATH": f"/function/function_code{self.file_extension}",
                            "FUNCTION_NAME": function_name,
                            "INPUT_DATA": json.dumps(input_data)
                        }
                    )
                    
                    # Execute the command
                    print(f"Starting exec command: {exec_cmd['Id'][:12]}")
                    exec_output = self.client.api.exec_start(exec_cmd['Id'])
                    exec_info = self.client.api.exec_inspect(exec_cmd['Id'])
                    logs = exec_output.decode('utf-8').strip()
                    print(f"Exec command completed with exit code: {exec_info.get('ExitCode')}")
                except Exception as e:
                    print(f"Error executing command in container: {e}")
                    print(traceback.format_exc())
                    # Fall back to creating a new container
                    using_pooled_container = False
                    container_name = f"function-{uuid.uuid4()}"
                    print(f"Falling back to new container: {container_name}")
                    container = self.client.containers.run(
                        self.base_image,
                        detach=True,
                        name=container_name,
                        volumes={
                            code_path: {
                                "bind": f"/function/function_code{self.file_extension}",
                                "mode": "ro"
                            }
                        },
                        environment={
                            "FUNCTION_PATH": f"/function/function_code{self.file_extension}",
                            "FUNCTION_NAME": function_name,
                            "INPUT_DATA": json.dumps(input_data)
                        },
                        mem_limit="128m",
                        cpu_quota=100000,
                        network_mode="none"
                    )
                    container_id = container.id
            
            # Wait for the container to finish or timeout
            try:
                if not using_pooled_container:
                    print(f"Waiting for container {container_id[:12]} to complete")
                    exit_code = container.wait(timeout=timeout)["StatusCode"]
                    logs = container.logs().decode("utf-8").strip()
                    print(f"Container completed with exit code: {exit_code}")
                execution_time = time.time() - start_time
                
                # Parse the output
                try:
                    print(f"Parsing output: {logs[:100]}...")
                    result = json.loads(logs)
                    result["execution_time"] = execution_time
                    result["container_id"] = container_id
                    result["warm_start"] = using_pooled_container
                    return result
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON: {e}")
                    return {
                        "status": "error",
                        "error": "Failed to parse function output",
                        "logs": logs,
                        "execution_time": execution_time,
                        "warm_start": using_pooled_container
                    }
                    
            except Exception as e:
                # Handle timeout
                print(f"Error waiting for container: {e}")
                execution_time = time.time() - start_time
                return {
                    "status": "error",
                    "error": f"Function execution failed or timed out: {str(e)}",
                    "execution_time": execution_time,
                    "warm_start": using_pooled_container
                }
                
        finally:
            # Clean up
            if not using_pooled_container and container_id:
                try:
                    print(f"Cleaning up container: {container_id[:12]}")
                    if container:
                        container.remove(force=True)
                except Exception as e:
                    print(f"Error removing container: {e}")
            elif using_pooled_container and container_id and self.container_pool:
                # Return container to the pool
                print(f"Returning container to pool: {container_id[:12]}")
                self.container_pool.release_container(container_id)
                
            # Remove temporary files
            try:
                os.remove(code_path)
                os.rmdir(temp_dir)
            except Exception as e:
                print(f"Error removing temp files: {e}")
    
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
            # Building the image from the Dockerfile
            build_path = os.path.join(os.getcwd(), "docker")
            
            dockerfile = "Dockerfile.python"
            if self.language == "javascript":
                dockerfile = "Dockerfile.javascript"
                
            self.client.images.build(
                path=build_path,
                dockerfile=dockerfile,
                tag=self.base_image
            )
            print(f"Image {self.base_image} built successfully")
    
    def shutdown(self):
        """Shut down the runtime and container pool"""
        if self.container_pool:
            self.container_pool.shutdown()