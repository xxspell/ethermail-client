# task_manager.py
from typing import Dict, Optional, List
from datetime import datetime
import asyncio
from enum import Enum


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RegistrationTask:
    def __init__(self, proxies: List[str], count: int = 1):
        self.proxies = proxies
        self.count = count
        self.status = TaskStatus.PENDING
        self.created_at = datetime.utcnow()
        self.completed_count = 0
        self.failed_count = 0
        self.results = []
        self.errors = []


class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, RegistrationTask] = {}
        self._task_counter = 0

    def create_task(self, proxies: List[str], count: int = 1) -> str:
        self._task_counter += 1
        task_id = f"task_{self._task_counter}"
        self.tasks[task_id] = RegistrationTask(proxies, count)
        return task_id

    def get_task(self, task_id: str) -> Optional[RegistrationTask]:
        return self.tasks.get(task_id)


