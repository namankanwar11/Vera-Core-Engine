import asyncio
from typing import Dict, Any, Tuple
import time

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
                "category": len(self.data["category"]),
                "merchant": len(self.data["merchant"]),
                "customer": len(self.data["customer"]),
                "trigger": len(self.data["trigger"])
            }
            
    async def push_context(self, scope: str, context_id: str, version: int, payload: Any) -> Tuple[bool, bool, int]:
        """
        Pushes a context into the store.
        Returns a tuple: (accepted: bool, is_duplicate: bool, current_version: int)
        """
        async with self.lock:
            if scope not in self.data:
                self.data[scope] = {}
                
            current = self.data[scope].get(context_id)
            if current:
                if current["version"] > version:
                    return False, False, current["version"] # Stale version
                elif current["version"] == version:
                    return True, True, current["version"] # Duplicate version, accepted as no-op
                
            self.data[scope][context_id] = {
                "version": version,
                "payload": payload
            }
            return True, False, version

    async def get_context(self, scope: str, context_id: str) -> Any:
        async with self.lock:
            current = self.data.get(scope, {}).get(context_id)
            if current:
                return current["payload"]
            return None

store = MemoryStateStore()
