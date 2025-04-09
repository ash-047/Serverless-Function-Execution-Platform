import threading
import time
import docker
import uuid
import platform
import io
import tarfile
from typing import Dict, List, Optional
import queue

class ContainerPool:
    def __init__(self, base_image: str, min_pool_size: int = 2, max_pool_size: int = 5, 
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
        
        # Determine the language based on the image name
        self.language = "javascript" if "javascript" in base_image else "python"
        print(f"Container pool initialized for {self.language} with {base_image}")
        
        self.containers: Dict[str, Dict] = {}
        self.container_metrics: Dict[str, Dict] = {}
        self.container_queue = queue.Queue()
        
        self.running = True
        self.pool_manager = threading.Thread(target=self._manage_pool)
        self.pool_manager.daemon = True
        self.pool_manager.start()
        
        if self.warm_up:
            print(f"Warming up {self.min_pool_size} containers for {self.language}")
            success_count = 0
            for _ in range(self.min_pool_size):
                container_id = self._create_container(pre_warm=True)
                if container_id:
                    self.container_queue.put(container_id)
                    success_count += 1
                else:
                    print(f"Failed to create warm-up container for {self.language}")
            
            # If we couldn't create any containers, log a warning
            if success_count == 0 and self.min_pool_size > 0:
                print(f"WARNING: Failed to create any warm-up containers for {self.language}. Container pool may not function correctly.")
        
    def _create_container(self, pre_warm=False) -> Optional[str]:
        """Create a new container and add it to the pool."""
        try:
            container_name = f"pool-{self.language}-{uuid.uuid4()}"
            
            # Choose a keep-alive command that prevents the container from exiting.
            if self.language == "javascript":
                # For Node.js containers: use a command that runs an interval.
                keep_alive_cmd = ["node", "-e", "setInterval(() => {}, 1000)"]
            else:
                # For Python containers: use a simple command to keep the container alive.
                # Using 'tail -f /dev/null' is a common trick.
                keep_alive_cmd = ["tail", "-f", "/dev/null"]

            # Override the image’s default ENTRYPOINT by explicitly passing entrypoint=""
            container = self.client.containers.run(
                image=self.base_image,
                name=container_name,
                detach=True,
                command=keep_alive_cmd,
                entrypoint="",  # force override of the image's default entrypoint
                mem_limit="128m",
                cpu_quota=50000,
                network_mode="bridge",
                remove=False  # Don't auto-remove so we can reuse it
            )
            
            # Wait a moment to ensure the container is fully started
            time.sleep(10)  # Adjust this wait time if necessary
            
            # Check if container is actually running
            container.reload()
            if container.status != "running":
                print(f"Container {container.id[:12]} failed to start, status: {container.status}")
                try:
                    container.remove(force=True)
                except Exception:
                    pass
                return None
                
            container_id = container.id
            self.containers[container_id] = {
                "id": container_id,
                "name": container_name,
                "status": "idle",
                "created_at": time.time(),
                "last_used": time.time(),
                "language": self.language
            }
            
            self.container_metrics[container_id] = {
                "executions": 0,
                "avg_response_time": 0,
                "total_exec_time": 0,
                "errors": 0
            }
            
            print(f"Created container {container_id[:12]} ({self.language}) - Status: {container.status}")
            return container_id
        except Exception as e:
            print(f"Error creating container: {e}")
            return None
        
    def _manage_pool(self):
        """Background thread to manage the pool size."""
        failure_count = 0
        while self.running:
            try:
                active_count = len(self.containers)
                
                # Create more containers if we're below minimum size
                if active_count < self.min_pool_size:
                    print(f"Pool below minimum size ({active_count}/{self.min_pool_size}), creating more containers")
                    
                    # Limit container creation attempts based on consecutive failures
                    max_attempts = 1 if failure_count > 5 else self.min_pool_size - active_count
                    
                    for _ in range(min(max_attempts, self.min_pool_size - active_count)):
                        if len(self.containers) < self.max_pool_size:
                            container_id = self._create_container()
                            if container_id:
                                self.container_queue.put(container_id)
                                failure_count = 0  # Reset failure count on success
                            else:
                                failure_count += 1  # Increment failure count
                
                # Remove idle containers that exceed timeout or are not running
                current_time = time.time()
                to_remove = []
                
                for container_id, container_data in list(self.containers.items()):
                    # Check container is still valid
                    try:
                        container = self.client.containers.get(container_id)
                        container.reload()  # Make sure we have latest status
                        if container.status != "running":
                            print(f"Container {container_id[:12]} is not running (status: {container.status})")
                            to_remove.append(container_id)
                        elif (container_data["status"] == "idle" and 
                              current_time - container_data["last_used"] > self.idle_timeout and
                              len(self.containers) > self.min_pool_size):
                            to_remove.append(container_id)
                    except docker.errors.NotFound:
                        # Container no longer exists
                        print(f"Container {container_id[:12]} not found, will be removed")
                        to_remove.append(container_id)
                    except Exception as e:
                        print(f"Error checking container {container_id[:12]}: {e}")
                        to_remove.append(container_id)
                
                for container_id in to_remove:
                    self._remove_container(container_id)
                    
            except Exception as e:
                print(f"Error in pool manager: {e}")
                failure_count += 1
            
            # Adaptive sleep based on failure count
            sleep_time = min(10 * (2 ** min(failure_count, 5)), 300)
            time.sleep(sleep_time)
    
    def get_container(self) -> Optional[str]:
        """Get an available container from the pool."""
        try:
            # First try to get container from queue
            container_id = self.container_queue.get(block=False)
            
            try:
                # Verify the container is still running
                container = self.client.containers.get(container_id)
                container.reload()  # Refresh status
                if container.status != "running":
                    print(f"Container {container_id[:12]} not running, attempting to restart it")
                    try:
                        container.start()
                        time.sleep(1)  # Give it time to start
                        container.reload()
                        if container.status != "running":
                            print(f"Failed to restart container {container_id[:12]}")
                            self._remove_container(container_id)
                            return self.get_container()  # Try another container
                    except Exception as e:
                        print(f"Error restarting container {container_id[:12]}: {e}")
                        self._remove_container(container_id)
                        return self.get_container()  # Try another container
                    
                # Mark as busy and update usage time
                self.containers[container_id]["status"] = "busy"
                self.containers[container_id]["last_used"] = time.time()
                print(f"Retrieved container {container_id[:12]} from pool")
                return container_id
            except Exception as e:
                print(f"Error getting container {container_id[:12]} from pool: {e}")
                self._remove_container(container_id)
                return self.get_container()  # Try another container
                
        except queue.Empty:
            # If queue is empty but we have space, create a new container
            if len(self.containers) < self.max_pool_size:
                print(f"Creating new container (pool size: {len(self.containers)})")
                container_id = self._create_container()
                if container_id:
                    self.containers[container_id]["status"] = "busy"
                    return container_id
                else:
                    # If we couldn't create a container, create a one-off container outside the pool
                    print("Failed to create container for pool, returning None")
            else:
                print(f"Container pool at maximum capacity ({self.max_pool_size})")
            return None
    
    def release_container(self, container_id: str, execution_stats: Dict = None):
        """Return a container to the pool after use."""
        if container_id in self.containers:
            try:
                # Update metrics if execution stats provided
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
                
                # Check if container is still valid
                container = self.client.containers.get(container_id)
                container.reload()
                if container.status != "running":
                    print(f"Released container {container_id[:12]} not running, attempting to restart")
                    try:
                        container.start()
                        time.sleep(1)  # Give it time to start
                        container.reload()
                        if container.status != "running":
                            print(f"Failed to restart container {container_id[:12]}")
                            self._remove_container(container_id)
                            return
                    except Exception as e:
                        print(f"Error restarting container {container_id[:12]}: {e}")
                        self._remove_container(container_id)
                        return
                
                # Mark as idle and return to queue
                self.containers[container_id]["status"] = "idle"
                self.containers[container_id]["last_used"] = time.time()
                self.container_queue.put(container_id)
                print(f"Container {container_id[:12]} returned to pool")
                
            except Exception as e:
                print(f"Error releasing container {container_id[:12]}: {e}")
                self._remove_container(container_id)
    
    def copy_to_container(self, container_id: str, src_path: str, dest_path: str) -> bool:
        """Copy a file to a container."""
        try:
            # Create a tarfile in memory
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                tar.add(src_path, arcname=dest_path.split('/')[-1])
            
            tar_stream.seek(0)
            
            # Get directory part of the destination path
            dest_dir = '/'.join(dest_path.split('/')[:-1])
            if not dest_dir:
                dest_dir = '/'
                
            # Copy the tar stream to the container
            self.client.api.put_archive(container_id, dest_dir, tar_stream.read())
            return True
            
        except Exception as e:
            print(f"Error copying file to container {container_id[:12]}: {e}")
            return False
    
    def get_pool_metrics(self) -> Dict:
        """Get metrics about the container pool."""
        active_count = len(self.containers)
        idle_count = sum(1 for c in self.containers.values() if c["status"] == "idle")
        return {
            "total_containers": active_count,
            "idle_containers": idle_count,
            "busy_containers": active_count - idle_count,
            "queue_size": self.container_queue.qsize(),
            "language": self.language
        }
    
    def _remove_container(self, container_id: str):
        """Remove a container from the pool."""
        try:
            if container_id in self.containers:
                print(f"Removing container {container_id[:12]} from pool")
                try:
                    container = self.client.containers.get(container_id)
                    container.stop(timeout=1)
                    container.remove(force=True)
                except docker.errors.NotFound:
                    # Container already gone, that's fine
                    pass
                except Exception as e:
                    print(f"Error stopping/removing container {container_id[:12]}: {e}")
                
                # Remove from our data structures
                self.containers.pop(container_id, None)
                self.container_metrics.pop(container_id, None)
        except Exception as e:
            print(f"Error in _remove_container for {container_id[:12]}: {e}")
    
    def shutdown(self):
        """Shut down the pool and clean up all containers."""
        print(f"Shutting down container pool for {self.language}")
        self.running = False
        
        if self.pool_manager.is_alive():
            self.pool_manager.join(timeout=2)
        
        # Clean up all containers
        for container_id in list(self.containers.keys()):
            self._remove_container(container_id)