import threading
import time
import docker
import uuid
import platform
from typing import Dict, List, Optional
import queue

class ContainerPool:
    def __init__(self, base_image: str, min_pool_size: int = 3, max_pool_size: int = 10, 
                 idle_timeout: int = 300, warm_up: bool = True):
        try:
            if platform.system() == "Windows":
                self.client = docker.DockerClient(base_url='npipe:////./pipe/docker_engine')
                print("Using Windows named pipe for Docker connection")
            else:
                self.client = docker.from_env()
                print("Using default Docker connection")
        except Exception as e:
            print(f"Error connecting to Docker: {e}")
            raise
            
        self.base_image = base_image
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.idle_timeout = idle_timeout
        self.warm_up = warm_up
        
        self.containers: Dict[str, Dict] = {}
        self.container_metrics: Dict[str, Dict] = {}
        self.container_queue = queue.Queue()
        self.function_cache: Dict[str, Dict] = {}
        
        self.running = True
        self.pool_manager = threading.Thread(target=self._manage_pool)
        self.pool_manager.daemon = True
        self.pool_manager.start()
        
        if self.warm_up:
            self.warm_up_thread = threading.Thread(target=self._warm_up_containers)
            self.warm_up_thread.daemon = True
            self.warm_up_thread.start()
        
    def _create_container(self) -> str:
        container_name = f"pool-{uuid.uuid4()}"
        container = self.client.containers.create(
            image=self.base_image,
            name=container_name,
            detach=True,
            command=["sh", "-c", "while true; do sleep 10; done"],
            mem_limit="64m",
            cpu_quota=50000,
            network_disabled=False,
            restart_policy={"Name": "always"}
        )
            
        container_id = container.id
        self.containers[container_id] = {
            "container": container,
            "name": container_name,
            "status": "idle",
            "created_at": time.time(),
            "last_used": time.time()
        }
        
        self.container_metrics[container_id] = {
            "executions": 0,
            "avg_response_time": 0,
            "total_exec_time": 0,
            "errors": 0,
            "last_error": None
        }
        
        return container_id
        
    def _manage_pool(self):
        while self.running:
            try:
                active_count = len(self.containers)
                if active_count < self.min_pool_size:
                    for _ in range(self.min_pool_size - active_count):
                        if len(self.containers) < self.max_pool_size:
                            container_id = self._create_container()
                            self.containers[container_id]["container"].start()
                            self.container_queue.put(container_id)
                            print(f"Added container {container_id[:12]} to pool")
                
                current_time = time.time()
                to_remove = []
                
                for container_id, container_data in self.containers.items():
                    if (container_data["status"] == "idle" and 
                        current_time - container_data["last_used"] > self.idle_timeout and
                        len(self.containers) > self.min_pool_size):
                        to_remove.append(container_id)
                
                for container_id in to_remove:
                    self._remove_container(container_id)
                    
            except Exception as e:
                print(f"Error in pool manager: {e}")
            
            time.sleep(5)
    
    def _warm_up_containers(self):
        while self.running:
            try:
                if not self.function_cache:
                    dummy_functions = [
                        {"language": "python", "code": "def handler(event): return {'status': 'warm'}", "input": {}},
                        {"language": "javascript", "code": "function handler(event) { return {status: 'warm'}; }\nmodule.exports = { handler };", "input": {}}
                    ]
                    
                    current_time = time.time()
                    idle_containers = [
                        container_id for container_id, container_data in self.containers.items()
                        if container_data["status"] == "idle" and 
                        current_time - container_data["last_used"] > 30
                    ]
                    
                    for container_id in idle_containers[:2]:
                        try:
                            container_name = self.containers[container_id]["name"]
                            is_js = "js" in container_name or "javascript" in container_name
                            
                            dummy_fn = dummy_functions[1] if is_js else dummy_functions[0]
                            
                            print(f"Warming up container {container_id[:12]}")
                            self.containers[container_id]["last_used"] = time.time()
                        except Exception as e:
                            print(f"Error warming up container {container_id[:12]}: {e}")
                else:
                    pass
            except Exception as e:
                print(f"Error in warm-up thread: {e}")
            
            time.sleep(60)
            
    def get_container(self, language=None) -> Optional[str]:
        try:
            available = list(self.container_queue.queue)
            
            if len(available) > 1:
                if language:
                    language_filtered = [
                        c_id for c_id in available 
                        if (("js" in self.containers[c_id]["name"] or "javascript" in self.containers[c_id]["name"]) 
                            == (language.lower() == "javascript"))
                    ]
                    if language_filtered:
                        available = language_filtered
                
                if available:
                    available.sort(
                        key=lambda c_id: (
                            self.container_metrics.get(c_id, {}).get("avg_response_time", 0),
                            self.container_metrics.get(c_id, {}).get("errors", 0)
                        )
                    )
                    
                    best_container = available[0]
                    self.container_queue.queue.remove(best_container)
                    
                    self.containers[best_container]["status"] = "busy"
                    self.containers[best_container]["last_used"] = time.time()
                    return best_container
            
            container_id = self.container_queue.get(timeout=1)
            self.containers[container_id]["status"] = "busy"
            self.containers[container_id]["last_used"] = time.time()
            return container_id
        except queue.Empty:
            if len(self.containers) < self.max_pool_size:
                container_id = self._create_container()
                self.containers[container_id]["container"].start()
                self.containers[container_id]["status"] = "busy"
                return container_id
            else:
                return None
    
    def release_container(self, container_id: str, execution_stats: Dict = None):
        if container_id in self.containers:
            self.containers[container_id]["status"] = "idle"
            self.containers[container_id]["last_used"] = time.time()
            
            if execution_stats and container_id in self.container_metrics:
                metrics = self.container_metrics[container_id]
                metrics["executions"] += 1
                if "execution_time" in execution_stats:
                    exec_time = execution_stats["execution_time"]
                    total_time = metrics["total_exec_time"] + exec_time
                    metrics["total_exec_time"] = total_time
                    metrics["avg_response_time"] = total_time / metrics["executions"]

                if execution_stats.get("status") == "error":
                    metrics["errors"] += 1
                    metrics["last_error"] = execution_stats.get("error", "Unknown error")
        
            self.container_queue.put(container_id)
    
    def add_to_function_cache(self, function_hash: str, function_data: Dict):
        self.function_cache[function_hash] = function_data
        if len(self.function_cache) > 10:
            oldest = min(self.function_cache.items(), key=lambda x: x[1].get("last_used", 0))
            del self.function_cache[oldest[0]]
    
    def get_pool_metrics(self) -> Dict:
        active_count = len(self.containers)
        idle_count = sum(1 for c in self.containers.values() if c["status"] == "idle")
        return {
            "total_containers": active_count,
            "idle_containers": idle_count,
            "busy_containers": active_count - idle_count,
            "container_metrics": self.container_metrics,
            "queue_size": self.container_queue.qsize()
        }
    
    def _remove_container(self, container_id: str):
        try:
            container_data = self.containers.pop(container_id, None)
            if container_data:
                container = container_data["container"]
                container.stop()
                container.remove()
                print(f"Removed idle container {container_id[:12]} from pool")
                if container_id in self.container_metrics:
                    del self.container_metrics[container_id]
        except Exception as e:
            print(f"Error removing container {container_id[:12]}: {e}")
    
    def shutdown(self):
        self.running = False
        if self.pool_manager.is_alive():
            self.pool_manager.join(timeout=5)
        for container_id in list(self.containers.keys()):
            self._remove_container(container_id)
