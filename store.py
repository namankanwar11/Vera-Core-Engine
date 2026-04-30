import asyncio
import json
import os
import time
from typing import Dict, Any, Tuple

STATE_FILE = "state.json"

class MemoryStateStore:
    def __init__(self):
        self.lock = asyncio.Lock()
        # Storage format: scope -> context_id -> {"version": int, "payload": Any}
        self.data: Dict[str, Dict[str, Dict[str, Any]]] = {
            "category": {},
            "merchant": {},
            "trigger": {},
            "customer": {}
        }
        self.start_time = time.time()
        self.events = [] # Real-time event buffer
        self.metrics = {
            "score": 0,
            "specificity": 0,
            "category_fit": 0,
            "messages_sent": 0,
            "performance_text": "Waiting for first evaluation..."
        }
        self._load_from_disk()

    def _save_state(self):
        try:
            # Deep conversion of Pydantic models to serializable dicts
            serializable_state = {
                "merchants": {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in self.merchants.items()},
                "triggers": {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in self.triggers.items()},
                "categories": {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in self.categories.items()},
                "customers": {k: (v.model_dump() if hasattr(v, "model_dump") else v) for k, v in self.customers.items()},
                "events": self.events,
                "metrics": self.metrics
            }
            with open(self.state_file, "w") as f:
                json.dump(serializable_state, f)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _load_from_disk(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    content = json.load(f)
                    self.data.update(content.get("data", {}))
                    self.metrics.update(content.get("metrics", {}))
            except Exception as e:
                print(f"Failed to load state: {e}")

    def add_event(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.events.append(f"[{timestamp}] {message}")
        if len(self.events) > 15:
            self.events.pop(0)
        
    def get_uptime(self) -> int:
        return int(time.time() - self.start_time)
        
    async def get_counts(self) -> Dict[str, int]:
        async with self.lock:
            return {
                "category": len(self.data.get("category", {})),
                "merchant": len(self.data.get("merchant", {})),
                "customer": len(self.data.get("customer", {})),
                "trigger": len(self.data.get("trigger", {}))
            }
            
    async def push_context(self, scope: str, context_id: str, version: int, payload: Any) -> Tuple[bool, bool, int]:
        async with self.lock:
            if scope not in self.data:
                self.data[scope] = {}
                
            current = self.data[scope].get(context_id)
            if current:
                if current["version"] > version:
                    return False, False, current["version"]
                elif current["version"] == version:
                    return True, True, current["version"]
                
            self.data[scope][context_id] = {
                "version": version,
                "payload": payload
            }
            self._save_to_disk()
            return True, False, version

    async def get_context(self, scope: str, context_id: str) -> Any:
        async with self.lock:
            current = self.data.get(scope, {}).get(context_id)
            if current:
                return current["payload"]
            return None

    def report_score(self, metrics: Dict[str, Any]):
        self.metrics.update(metrics)
        self._save_to_disk()

store = MemoryStateStore()
