import json
import os
import threading
from datetime import datetime, timezone
from uuid import uuid4

from .logging_util import ProjectLogger

logger = ProjectLogger.get_logger(__name__)


class ConversationStore:
    def __init__(self, filepath="conversations.json"):
        self.filepath = filepath
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath) as f:
                    self.data = json.load(f)
                logger.info(f"Loaded {len(self.data.get('conversations', []))} conversations from {self.filepath}")
            except Exception as e:
                logger.warning(f"Failed to load conversations file: {e}")
                self.data = {"conversations": []}
        else:
            self.data = {"conversations": []}

    def _save(self):
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)

    def _now(self):
        return datetime.now(timezone.utc).isoformat()

    def list_conversations(self, device_id):
        with self.lock:
            convs = [c for c in self.data["conversations"] if c.get("device_id") == device_id]
            result = []
            for c in sorted(convs, key=lambda x: x.get("updated_at", ""), reverse=True):
                result.append({
                    "id": c["id"],
                    "title": c.get("title", ""),
                    "model": c.get("model", "meta-model"),
                    "msg_count": len(c.get("messages", [])),
                    "created_at": c.get("created_at", ""),
                    "updated_at": c.get("updated_at", ""),
                })
            return result

    def get_conversation(self, device_id, conv_id):
        with self.lock:
            for c in self.data["conversations"]:
                if c["id"] == conv_id and c.get("device_id") == device_id:
                    return c
            return None

    def create_conversation(self, device_id, model="meta-model"):
        now = self._now()
        conv = {
            "id": "conv_" + uuid4().hex[:12],
            "device_id": device_id,
            "title": "",
            "model": model,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        with self.lock:
            self.data["conversations"].append(conv)
            self._save()
        return {"id": conv["id"]}

    def update_conversation(self, device_id, conv_id, data):
        with self.lock:
            for c in self.data["conversations"]:
                if c["id"] == conv_id and c.get("device_id") == device_id:
                    if "title" in data:
                        c["title"] = data["title"]
                    if "model" in data:
                        c["model"] = data["model"]
                    if "messages" in data:
                        c["messages"] = data["messages"]
                    c["updated_at"] = self._now()
                    self._save()
                    return True
            return False

    def delete_conversation(self, device_id, conv_id):
        with self.lock:
            for i, c in enumerate(self.data["conversations"]):
                if c["id"] == conv_id and c.get("device_id") == device_id:
                    self.data["conversations"].pop(i)
                    self._save()
                    return True
            return False

    def import_conversations(self, device_id, conversations):
        with self.lock:
            existing_ids = {c["id"] for c in self.data["conversations"] if c.get("device_id") == device_id}
            count = 0
            for conv in conversations:
                if not isinstance(conv, dict) or "id" not in conv:
                    continue
                if conv["id"] not in existing_ids:
                    conv["device_id"] = device_id
                    self.data["conversations"].append(conv)
                    existing_ids.add(conv["id"])
                    count += 1
            if count > 0:
                self._save()
            return {"imported": count}
