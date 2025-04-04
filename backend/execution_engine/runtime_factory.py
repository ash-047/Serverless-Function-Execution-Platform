import docker
import json
import os
import platform
import subprocess
from typing import Dict, Any, Optional

class RuntimeFactory:
    """Factory for creating different container runtimes"""
    
    @staticmethod
    def create_runtime(runtime_type: str, language: str = "python", **kwargs):
        """
        Create a runtime based on the specified type.
        
        Args:
            runtime_type: Type of runtime to create ('docker', 'gvisor')
            language: Programming language ('python', 'javascript')
            **kwargs: Additional arguments for the runtime
            
        Returns:
            A runtime instance
        """
        from .docker_runtime import DockerRuntime
        
        # Default image base names
        python_images = {"docker": "python-function:latest", "gvisor": "python-function:latest"}
        javascript_images = {"docker": "javascript-function:latest", "gvisor": "javascript-function:latest"}
        
        # Select the right image based on language and runtime
        if language.lower() == "javascript":
            image = javascript_images.get(runtime_type.lower(), javascript_images["docker"])
        else:
            image = python_images.get(runtime_type.lower(), python_images["docker"])
        
        # Create the appropriate runtime
        if runtime_type.lower() == "gvisor":
            # Check if gVisor is available before creating the gVisor runtime
            is_available = RuntimeFactory.is_gvisor_available()
            if is_available:
                print("Using gVisor runtime")
                return GVisorRuntime(base_image=image, language=language, **kwargs)
            else:
                print("gVisor runtime requested but not available. Falling back to Docker runtime.")
                return DockerRuntime(base_image=image, language=language, **kwargs)
        else:
            return DockerRuntime(base_image=image, language=language, **kwargs)
    
    @staticmethod
    def is_gvisor_available():
        """Check if gVisor is available on the system"""
        try:
            # Check if runsc runtime is registered with Docker
            client = docker.from_env()
            info = client.info()
            runtimes = info.get('Runtimes', {})
            gvisor_available = 'runsc' in runtimes
            print(f"gVisor availability check: {'Available' if gvisor_available else 'Not available'}")
            return gvisor_available
        except Exception as e:
            print(f"Error checking gVisor availability: {e}")
            return False

class GVisorRuntime:
    """Docker runtime with gVisor for additional isolation"""
    
    def __init__(self, base_image="python-function:latest", timeout=60, use_pool=False, language="python"):
        """
        Initialize the gVisor runtime.
        
        Args:
            base_image: The Docker image to use for function execution
            timeout: Default timeout for function execution in seconds
            use_pool: Whether to use the container pool for warm starts
            language: The programming language ("python" or "javascript")
        """
        # Import here to avoid circular imports
        from .docker_runtime import DockerRuntime
        
        # Create a standard Docker runtime but specify gVisor runtime
        self.docker_runtime = DockerRuntime(base_image=base_image, timeout=timeout, use_pool=use_pool, language=language)
        
        # Override runtime to use gVisor if available
        self.using_gvisor = RuntimeFactory.is_gvisor_available()
        self.runtime_type = "gvisor" if self.using_gvisor else "docker"
        
        # Log whether we're actually using gVisor
        if self.using_gvisor:
            print(f"GVisorRuntime initialized with gVisor for {language}")
        else:
            print(f"GVisorRuntime initialized with Docker fallback for {language} (gVisor not available)")
        
        # Store for metrics
        self.language = language
    
    def execute_function(self, code, function_name="handler", input_data=None, timeout=None, **kwargs):
        """
        Execute a function using gVisor.
        
        Args:
            code: The function code as a string
            function_name: The name of the function to execute
            input_data: Input data to pass to the function
            timeout: Timeout for this specific execution
            **kwargs: Additional arguments
            
        Returns:
            A dictionary containing the execution result
        """
        # Double-check gVisor availability at runtime (it could have changed)
        self.using_gvisor = RuntimeFactory.is_gvisor_available()
        self.runtime_type = "gvisor" if self.using_gvisor else "docker"
        
        # Log which runtime is being used for this execution
        if self.using_gvisor:
            print(f"Executing {self.language} function with gVisor runtime")
        else:
            print(f"Executing {self.language} function with Docker runtime (fallback mode)")
        
        # Use the docker runtime with gVisor-specific options
        result = self.docker_runtime.execute_function(
            code=code,
            function_name=function_name,
            input_data=input_data,
            timeout=timeout,
            runtime="runsc" if self.using_gvisor else None,  # Use gVisor runtime if available
            **kwargs
        )
        
        # Add runtime type to result for metrics
        if isinstance(result, dict):
            result["runtime"] = self.runtime_type
            result["language"] = self.language
            
        return result
    
    def preload_image(self):
        """Ensure the base image is available locally"""
        return self.docker_runtime.preload_image()
    
    def shutdown(self):
        """Shut down the runtime"""
        return self.docker_runtime.shutdown()
