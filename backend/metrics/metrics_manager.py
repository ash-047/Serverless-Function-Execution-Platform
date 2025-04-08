import time
import threading
import json
import os
from typing import Dict, List, Any#, Optional
from collections import defaultdict
import datetime

class MetricsManager:
    def __init__(self, storage_dir: str = None, max_records: int = 1000):
        self.executions = []
        self.execution_lock = threading.Lock()
        self.max_records = max_records
        self.metrics = {
            "total_executions": 0,
            "successful_executions": 0,
            "failed_executions": 0,
            "total_execution_time": 0,
            "avg_execution_time": 0,
            "cold_starts": 0,
            "warm_starts": 0,
            "by_language": defaultdict(lambda: {
                "count": 0,
                "success": 0,
                "errors": 0,
                "avg_time": 0,
                "total_time": 0
            }),
            "by_runtime": defaultdict(lambda: {
                "count": 0,
                "success": 0,
                "errors": 0,
                "avg_time": 0,
                "total_time": 0 
            }),
            "hourly_stats": defaultdict(int)
        }
        if storage_dir:
            self.storage_dir = storage_dir
            os.makedirs(storage_dir, exist_ok=True)
        else:
            self.storage_dir = None
        self.running = True
        self.aggregation_thread = threading.Thread(target=self._periodic_aggregation)
        self.aggregation_thread.daemon = True
        self.aggregation_thread.start()
    
    def record_execution(self, execution_data: Dict[str, Any]):
        if "timestamp" not in execution_data:
            execution_data["timestamp"] = time.time()
        
        with self.execution_lock:
            self.executions.append(execution_data)
            if len(self.executions) > self.max_records:
                self.executions.pop(0)
            self._update_metrics(execution_data)
            if self.storage_dir:
                self._save_execution(execution_data)
    
    def _update_metrics(self, execution_data: Dict[str, Any]):
        metrics = self.metrics
        metrics["total_executions"] += 1
        if execution_data.get("status") == "success":
            metrics["successful_executions"] += 1
        else:
            metrics["failed_executions"] += 1
        if "execution_time" in execution_data:
            exec_time = execution_data["execution_time"]
            metrics["total_execution_time"] += exec_time
            metrics["avg_execution_time"] = metrics["total_execution_time"] / metrics["total_executions"]
        
        if execution_data.get("warm_start", False):
            metrics["warm_starts"] += 1
        else:
            metrics["cold_starts"] += 1

        language = execution_data.get("language", "unknown")
        lang_metrics = metrics["by_language"][language]
        lang_metrics["count"] += 1

        if execution_data.get("status") == "success":
            lang_metrics["success"] += 1
        else:
            lang_metrics["errors"] += 1

        if "execution_time" in execution_data:
            exec_time = execution_data["execution_time"]
            lang_metrics["total_time"] += exec_time
            lang_metrics["avg_time"] = lang_metrics["total_time"] / lang_metrics["count"]

        runtime = execution_data.get("runtime", "docker")
        runtime_metrics = metrics["by_runtime"][runtime]
        runtime_metrics["count"] += 1
        
        if execution_data.get("status") == "success":
            runtime_metrics["success"] += 1
        else:
            runtime_metrics["errors"] += 1
            
        if "execution_time" in execution_data:
            exec_time = execution_data["execution_time"]
            runtime_metrics["total_time"] += exec_time
            runtime_metrics["avg_time"] = runtime_metrics["total_time"] / runtime_metrics["count"]
        
        timestamp = execution_data.get("timestamp", time.time())
        hour = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:00")
        metrics["hourly_stats"][hour] += 1
    
    def _save_execution(self, execution_data: Dict[str, Any]):
        if not self.storage_dir:
            return
        try:
            timestamp = execution_data.get("timestamp", time.time())
            date_str = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
            filename = os.path.join(self.storage_dir, f"executions_{date_str}.jsonl")
            with open(filename, "a") as f:
                f.write(json.dumps(execution_data) + "\n")
        except Exception as e:
            print(f"Error saving execution data: {e}")
    
    def _periodic_aggregation(self):
        while self.running:
            try:
                if self.storage_dir:
                    metrics_file = os.path.join(self.storage_dir, "aggregated_metrics.json")
                    with open(metrics_file, "w") as f:
                        json.dump(self.metrics, f, indent=2, default=lambda x: dict(x) if isinstance(x, defaultdict) else x)
            except Exception as e:
                print(f"Error in periodic aggregation: {e}")
            time.sleep(60) 
    
    def get_metrics(self) -> Dict[str, Any]:
        with self.execution_lock:
            metrics_copy = json.loads(json.dumps(self.metrics, default=lambda x: dict(x) if isinstance(x, defaultdict) else x))
            return metrics_copy
    
    def get_recent_executions(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self.execution_lock:
            return self.executions[-limit:]
    
    def get_executions_by_criteria(self, criteria: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        with self.execution_lock:
            filtered = []
            for execution in reversed(self.executions):  
                matches = True
                for key, value in criteria.items():
                    if key not in execution or execution[key] != value:
                        matches = False
                        break
                if matches:
                    filtered.append(execution)
                    if len(filtered) >= limit:
                        break
            return filtered
    
    def shutdown(self):
        self.running = False
        if self.aggregation_thread.is_alive():
            self.aggregation_thread.join(timeout=5)
