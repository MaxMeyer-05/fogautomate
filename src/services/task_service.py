from typing import List
from datetime import datetime

from src.api.api_manager import api
from src.models.task import FogTask

from src.logger.logger import LogManager
logging = LogManager.get_logger("task_service")

class TaskService:
    """
    Service for managing Image tasks, including fetching active tasks, canceling hung tasks, and clearing failed tasks.
    """
    
    def fetch_active_tasks(self) -> List[FogTask]:
        """
        Fetches the list of active tasks from the FOG API.
        Returns:
            List[FogTask]: A list of active FogTask objects.
        """
        success, response = api.execute_fog_request("GET", "task/active")
        if not success or not response:
            return []
            
        active_tasks = response.get('tasks', [])
        if isinstance(active_tasks, dict):
            active_tasks = list(active_tasks.values())
            
        tasks = []
        for t in active_tasks:
            host_id = int(str(t.get('hostID', '0')))
            if host_id == 0:
                continue
                
            created_time = None
            start_time_str = t.get('createdTime', '')
            if start_time_str:
                try:
                    created_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    logging.error(f"Could not parse task start time: '{start_time_str}'")
                    
            tasks.append(FogTask(
                id=int(str(t.get('id', '0'))),
                host_id=host_id,
                state_id=int(str(t.get('stateID', '0'))),
                created_time=created_time
            ))
        return tasks

    def cancel_hung_task(self, task_id: int):
        """
        Cancels a hung task by sending a DELETE request to the FOG API.
        Args:
            task_id (int): The ID of the task to cancel.
        """
        api.execute_fog_request("DELETE", f"task/{task_id}/cancel")

    def clear_failed_task(self, task_id: int):
        """
        Clears a failed task by sending a DELETE request to the FOG API.
        Args:
            task_id (int): The ID of the task to clear.
        """
        api.execute_fog_request("DELETE", f"task/{task_id}")