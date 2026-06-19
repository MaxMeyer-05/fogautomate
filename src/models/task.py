from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class FogTask:
    """
    Represents a task in the fog computing environment.
    Args:
        id (int): The unique identifier of the task.
        host_id (int): The identifier of the host associated with the task.
        state_id (int): The identifier of the task's state.
        created_time (Optional[datetime]): The time when the task was created.
    """
    id: int
    host_id: int
    state_id: int
    created_time: Optional[datetime]
    
    @property
    def duration_minutes(self) -> int:
        if not self.created_time:
            return 0
        return int((datetime.now() - self.created_time).total_seconds() / 60)