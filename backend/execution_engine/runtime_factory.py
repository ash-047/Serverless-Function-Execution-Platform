import docker

class RuntimeFactory:
    @staticmethod
    def create_runtime(runtime_type: str, language: str = "python", **kwargs):
        from .docker_runtime import DockerRuntime
        python_images = {"docker": "python-function:latest", "gvisor": "python-function:latest"}
        javascript_images = {"docker": "javascript-function:latest", "gvisor": "javascript-function:latest"}
        if language.lower() == "javascript":
            image = javascript_images.get(runtime_type.lower(), javascript_images["docker"])
        else:
            image = python_images.get(runtime_type.lower(), python_images["docker"])
        if runtime_type.lower() == "gvisor":
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
        try:
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
    def __init__(self, base_image="python-function:latest", timeout=60, use_pool=False, language="python"):
        from .docker_runtime import DockerRuntime
        self.docker_runtime = DockerRuntime(base_image=base_image, timeout=timeout, use_pool=use_pool, language=language)
        self.using_gvisor = RuntimeFactory.is_gvisor_available()
        self.runtime_type = "gvisor" if self.using_gvisor else "docker"
        if self.using_gvisor:
            print(f"GVisorRuntime initialized with gVisor for {language}")
        else:
            print(f"GVisorRuntime initialized with Docker fallback for {language} (gVisor not available)")
        self.language = language
    
    def execute_function(self, code, function_name="handler", input_data=None, timeout=None, **kwargs):
        self.using_gvisor = RuntimeFactory.is_gvisor_available()
        self.runtime_type = "gvisor" if self.using_gvisor else "docker"
        if self.using_gvisor:
            print(f"Executing {self.language} function with gVisor runtime")
        else:
            print(f"Executing {self.language} function with Docker runtime (fallback mode)")
        result = self.docker_runtime.execute_function(
            code=code,
            function_name=function_name,
            input_data=input_data,
            timeout=timeout,
            runtime="runsc" if self.using_gvisor else None,  
            **kwargs
        )
        if isinstance(result, dict):
            result["runtime"] = self.runtime_type
            result["language"] = self.language   
        return result
    
    def preload_image(self):
        return self.docker_runtime.preload_image()
    
    def shutdown(self):
        return self.docker_runtime.shutdown()
