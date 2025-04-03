import threading
import time
import docker
import uuid
import platform
from typing import Dict, List, Optional
import queue
import json
import os
import random

class ContainerPool:
    def __init__(self, base_image: str, min_pool_size: int = 3, max_pool_size: int = 10, 
                 idle_timeout: int = 300, warm_up: bool = True):
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
        self.warm_up = warm_up
        
        # Container pool with last used timestamp
        self.containers: Dict[str, Dict] = {}
        
        # Track container performance metrics
        self.container_metrics: Dict[str, Dict] = {}
        
        # Queue for acquiring containers
        self.container_queue = queue.Queue()
        
        # Function cache for warm-up
        self.function_cache: Dict[str, Dict] = {}
        
        # Start background threads
        self.running = True
        self.pool_manager = threading.Thread(target=self._manage_pool)
        self.pool_manager.daemon = True
        self.pool_manager.start()
        
        # Start warm-up thread if enabled
        if self.warm_up:
            self.warm_up_thread = threading.Thread(target=self._warm_up_containers)
            self.warm_up_thread.daemon = True
            self.warm_up_thread.start()
        
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
        
        # Initialize metrics for this container
        self.container_metrics[container_id] = {
            "executions": 0,
            "avg_response_time": 0,
            "total_exec_time": 0,
            "errors": 0,
            "last_error": None
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
    
    def _warm_up_containers(self):
        """Pre-warm containers by running simple functions"""
        while self.running:
            try:
                # Check if we have cached functions to warm up with
                if not self.function_cache:
                    # Use a simple dummy function if no cache exists
                    dummy_functions = [
                        {"language": "python", "code": "def handler(event): return {'status': 'warm'}", "input": {}},
                        {"language": "javascript", "code": "function handler(event) { return {status: 'warm'}; }\nmodule.exports = { handler };", "input": {}}
                    ]
                    
                    # Only warm up containers that have been idle for a while
                    current_time = time.time()
                    idle_containers = [
                        container_id for container_id, container_data in self.containers.items()
                        if container_data["status"] == "idle" and 
                        current_time - container_data["last_used"] > 30  # Only warm up if idle for > 30s
                    ]
                    
                    for container_id in idle_containers[:2]:  # Limit to 2 containers per cycle
                        try:
                            # Get corresponding language for container
                            container_name = self.containers[container_id]["name"]
                            is_js = "js" in container_name or "javascript" in container_name
                            
                            dummy_fn = dummy_functions[1] if is_js else dummy_functions[0]
                            
                            # Use the container client to execute the dummy function
                            print(f"Warming up container {container_id[:12]}")
                            # Actual execution would happen here if we were executing
                            # Just simulate a warm-up by updating timestamps
                            self.containers[container_id]["last_used"] = time.time()
                        except Exception as e:
                            print(f"Error warming up container {container_id[:12]}: {e}")
                else:
                    # Use cached functions for warm-up
                    # Implementation depends on how real function execution works
                    pass
            except Exception as e:
                print(f"Error in warm-up thread: {e}")
            
            # Sleep between warm-up cycles
            time.sleep(60)  # Warm up every minute
            
    def get_container(self, language=None) -> Optional[str]:
        """
        Get a container from the pool or create a new one.
        
        Args:
            language: Optional language to filter containers
        
        Returns:
            Container ID or None if no container is available
        """
        try:
            # Get all available containers
            available = list(self.container_queue.queue)
            
            # If we have multiple containers available, use intelligent routing
            if len(available) > 1:
                # Filter by language if specified
                if language:
                    language_filtered = [
                        c_id for c_id in available 
                        if (("js" in self.containers[c_id]["name"] or "javascript" in self.containers[c_id]["name"]) 
                            == (language.lower() == "javascript"))
                    ]
                    if language_filtered:
                        available = language_filtered
                
                # Find the best container based on metrics
                if available:
                    # Sort by performance metrics (lower avg response time is better)
                    available.sort(
                        key=lambda c_id: (
                            self.container_metrics.get(c_id, {}).get("avg_response_time", 0),
                            self.container_metrics.get(c_id, {}).get("errors", 0)
                        )
                    )
                    
                    # Get the best container
                    best_container = available[0]
                    self.container_queue.queue.remove(best_container)
                    
                    # Update container status
                    self.containers[best_container]["status"] = "busy"
                    self.containers[best_container]["last_used"] = time.time()
                    return best_container
            
            # Fall back to queue get if intelligent routing doesn't find a container
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
    
    def release_container(self, container_id: str, execution_stats: Dict = None):
        """
        Return a container to the pool.
        
        Args:
            container_id: ID of the container to release
            execution_stats: Optional stats about the execution
        """
        if container_id in self.containers:
            self.containers[container_id]["status"] = "idle"
            self.containers[container_id]["last_used"] = time.time()
            
            # Update metrics if stats provided
            if execution_stats and container_id in self.container_metrics:
                metrics = self.container_metrics[container_id]
                
                # Update execution count
                metrics["executions"] += 1
                
                # Update average response time
                if "execution_time" in execution_stats:
                    exec_time = execution_stats["execution_time"]
                    total_time = metrics["total_exec_time"] + exec_time
                    metrics["total_exec_time"] = total_time
                    metrics["avg_response_time"] = total_time / metrics["executions"]
                
                # Track errors
                if execution_stats.get("status") == "error":
                    metrics["errors"] += 1
                    metrics["last_error"] = execution_stats.get("error", "Unknown error")
            
            # Add back to queue
            self.container_queue.put(container_id)
    
    def add_to_function_cache(self, function_hash: str, function_data: Dict):
        """Add a function to the cache for warm-ups"""
        self.function_cache[function_hash] = function_data
        
        # Limit cache size
        if len(self.function_cache) > 10:
            # Remove least recently used function
            oldest = min(self.function_cache.items(), key=lambda x: x[1].get("last_used", 0))
            del self.function_cache[oldest[0]]
    
    def get_pool_metrics(self) -> Dict:
        """Get metrics for the container pool"""
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
        """Remove a container from the pool"""
        try:
            container_data = self.containers.pop(container_id, None)
            if container_data:
                container = container_data["container"]
                container.stop()
                container.remove()
                print(f"Removed idle container {container_id[:12]} from pool")
                
                # Clean up metrics
                if container_id in self.container_metrics:
                    del self.container_metrics[container_id]
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
