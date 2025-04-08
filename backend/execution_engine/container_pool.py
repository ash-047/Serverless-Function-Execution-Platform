import threading
import time
import docker
import uuid
import platform
from typing import Dict, List, Optional
import queue

class ContainerPool:
    def __init__(self, base_image: str, min_pool_size: int = 3, max_pool_size: int = 10, 
                 idle_timeout: int = 300):
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
        self.containers: Dict[str, Dict] = {}
        self.container_queue = queue.Queue()
        self.running = True
        self.pool_manager = threading.Thread(target=self._manage_pool)
        self.pool_manager.daemon = True
        self.pool_manager.start()
        
    def _create_container(self) -> str:
        container_name = f"pool-{uuid.uuid4()}"
        container = self.client.containers.create(
            image=self.base_image,
            name=container_name,
            detach=True,
            mem_limit="64m",
            cpu_quota=50000,  # 5% of CPU
            network_disabled=True,
            command="sleep infinity"  # keep container running
        )
        
        container_id = container.id
        self.containers[container_id] = {
            "container": container,
            "name": container_name,
            "status": "idle",
            "created_at": time.time(),
            "last_used": time.time()
        }
        return container_id
        
    def _manage_pool(self):
        while self.running:
            try:
                # check pool size and create new containers if needed
                active_count = len(self.containers)
                if active_count < self.min_pool_size: # creating containers if there are lesser containers than min_pool_size
                    for _ in range(self.min_pool_size - active_count):
                        if len(self.containers) < self.max_pool_size:
                            container_id = self._create_container()
                            self.containers[container_id]["container"].start()
                            self.container_queue.put(container_id)
                            print(f"Added container {container_id[:12]} to pool")
                
                #clean up idle containers that exceed max idle time
                current_time = time.time()
                to_remove = []
                for container_id, container_data in self.containers.items():
                    if (container_data["status"] == "idle" and 
                        current_time - container_data["last_used"] > self.idle_timeout and
                        len(self.containers) > self.min_pool_size):
                        to_remove.append(container_id) # marking for removal
                for container_id in to_remove:
                    self._remove_container(container_id)
            except Exception as e:
                print(f"Error in pool manager: {e}")
            time.sleep(5)
    
    def get_container(self) -> Optional[str]:
        try:
            # try to get from queue with timeout
            container_id = self.container_queue.get(timeout=1)
            self.containers[container_id]["status"] = "busy"
            self.containers[container_id]["last_used"] = time.time()
            return container_id
        except queue.Empty:
            # if queue is empty but we haven't reached max size
            if len(self.containers) < self.max_pool_size:
                container_id = self._create_container()
                self.containers[container_id]["container"].start()
                self.containers[container_id]["status"] = "busy"
                return container_id
            else:
                return None
    
    def release_container(self, container_id: str):
        if container_id in self.containers:
            self.containers[container_id]["status"] = "idle"
            self.containers[container_id]["last_used"] = time.time()
            self.container_queue.put(container_id)
    
    def _remove_container(self, container_id: str):
        try:
            container_data = self.containers.pop(container_id, None)
            if container_data:
                container = container_data["container"]
                container.stop()
                container.remove()
                print(f"Removed idle container {container_id[:12]} from pool")
        except Exception as e:
            print(f"Error removing container {container_id[:12]}: {e}")
    
    def shutdown(self):
        self.running = False
        if self.pool_manager.is_alive():
            self.pool_manager.join(timeout=5)
        for container_id in list(self.containers.keys()):
            self._remove_container(container_id)
