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
        """
        Manage a pool of pre-warmed containers.
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
        except Exception as e:
            print(f"Error connecting to Docker: {e}")
            raise
            
        self.base_image = base_image
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.idle_timeout = idle_timeout
        
        # Container pool with last used timestamp
        self.containers: Dict[str, Dict] = {}
        
        # Queue for acquiring containers
        self.container_queue = queue.Queue()
        
        # Start background threads
        self.running = True
        self.pool_manager = threading.Thread(target=self._manage_pool)
        self.pool_manager.daemon = True
        self.pool_manager.start()
        
    def _create_container(self) -> str:
        """Create a new container and return its ID"""
        container_name = f"pool-{uuid.uuid4()}"
        container = self.client.containers.create(
            image=self.base_image,
            name=container_name,
            detach=True,
            # Basic container setup with minimal resources
            mem_limit="64m",
            cpu_quota=50000,  # 5% of CPU
            network_disabled=True,
            command="sleep infinity"  # Keep container running
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
        """Background thread to manage the container pool"""
        while self.running:
            try:
                # Check pool size and create new containers if needed
                active_count = len(self.containers)
                if active_count < self.min_pool_size:
                    # Create new containers to reach min_pool_size
                    for _ in range(self.min_pool_size - active_count):
                        if len(self.containers) < self.max_pool_size:
                            container_id = self._create_container()
                            # Start the container
                            self.containers[container_id]["container"].start()
                            # Add to available queue
                            self.container_queue.put(container_id)
                            print(f"Added container {container_id[:12]} to pool")
                
                # Clean up idle containers that exceed max idle time
                current_time = time.time()
                to_remove = []
                
                for container_id, container_data in self.containers.items():
                    if (container_data["status"] == "idle" and 
                        current_time - container_data["last_used"] > self.idle_timeout and
                        len(self.containers) > self.min_pool_size):
                        to_remove.append(container_id)
                
                # Remove containers marked for removal
                for container_id in to_remove:
                    self._remove_container(container_id)
                    
            except Exception as e:
                print(f"Error in pool manager: {e}")
            
            # Sleep to avoid high CPU usage
            time.sleep(5)
    
    def get_container(self) -> Optional[str]:
        """Get a container from the pool or create a new one"""
        try:
            # Try to get from queue with timeout
            container_id = self.container_queue.get(timeout=1)
            self.containers[container_id]["status"] = "busy"
            self.containers[container_id]["last_used"] = time.time()
            return container_id
        except queue.Empty:
            # If queue is empty but we haven't reached max size
            if len(self.containers) < self.max_pool_size:
                container_id = self._create_container()
                self.containers[container_id]["container"].start()
                self.containers[container_id]["status"] = "busy"
                return container_id
            else:
                return None
    
    def release_container(self, container_id: str):
        """Return a container to the pool"""
        if container_id in self.containers:
            self.containers[container_id]["status"] = "idle"
            self.containers[container_id]["last_used"] = time.time()
            self.container_queue.put(container_id)
    
    def _remove_container(self, container_id: str):
        """Remove a container from the pool"""
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
        """Shut down the container pool"""
        self.running = False
        # Wait for manager thread to finish
        if self.pool_manager.is_alive():
            self.pool_manager.join(timeout=5)
        
        # Clean up all containers
        for container_id in list(self.containers.keys()):
            self._remove_container(container_id)
