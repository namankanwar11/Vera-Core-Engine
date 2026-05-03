import asyncio
import json
import os
import time
import logging
from typing import Dict, Any, Tuple

STATE_FILE = "state.json"
logger = logging.getLogger("uvicorn.error")

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
        self.conversation_states: Dict[str, Dict[str, Any]] = {}
        self.start_time = time.time()
        self.events = []
        self.metrics = {
            "score": 0,
            "specificity": 0,
            "category_fit": 0,
            "messages_sent": 0,
            "performance_text": "Waiting for first evaluation..."
        }
        self._load_from_disk()

    async def _save_state(self):
        """Save state to disk in a background thread to avoid blocking the event loop."""
        try:
            def serialize(obj):
                if hasattr(obj, "model_dump"):
                    return obj.model_dump()
                return obj

            serializable_data = {
                "data": self.data,
                "metrics": self.metrics,
                "events": self.events,
                "conversation_states": self.conversation_states
            }
            
            def do_write():
                with open(STATE_FILE, "w") as f:
                    json.dump(serializable_data, f, default=serialize)
            
            await asyncio.to_thread(do_write)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _load_from_disk(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    content = json.load(f)
                    self.data.update(content.get("data", {}))
                    # Don't load old metrics/events — start fresh every boot
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

    def add_event(self, message: str):
        timestamp = time.strftime("%H:%M:%S")
        self.events.append(f"[{timestamp}] {message}")
        if len(self.events) > 15:
            self.events.pop(0)
        asyncio.create_task(self._save_state())

    def get_uptime(self) -> int:
        return int(time.time() - self.start_time)

    async def get_counts(self) -> Dict[str, int]:
        async with self.lock:
            return {k: len(v) for k, v in self.data.items()}

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
            await self._save_state()
            return True, False, version

    async def get_context(self, scope: str, context_id: str) -> Any:
        async with self.lock:
            current = self.data.get(scope, {}).get(context_id)
            if current:
                return current["payload"]
            return None

    def report_score(self, metrics: Dict[str, Any]):
        self.metrics.update(metrics)
        asyncio.create_task(self._save_state())

    def track_reply(self, conversation_id: str, message: str) -> int:
        """Track message repetitions. Returns count of identical consecutive messages."""
        msg_norm = message.lower().strip()
        state = self.conversation_states.get(conversation_id, {"last_msg": "", "count": 0})
        if state["last_msg"] == msg_norm:
            state["count"] += 1
        else:
            state["last_msg"] = msg_norm
            state["count"] = 1
        self.conversation_states[conversation_id] = state
        return state["count"]

store = MemoryStateStore()
