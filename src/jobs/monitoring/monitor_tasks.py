import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

root_path = Path(__file__).resolve().parent.parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import logging
from src.utils import db_session, fog_api_request
import src.notifications.mailer as mailer

def get_active_tasks() -> List[Dict[str, Any]]:
    """
    Retrieves the list of active tasks from the FOG API.
    Returns:
        List[Dict[str, Any]]: A list of active tasks with their details.
    """
    success, response = fog_api_request("GET", "task/active")
    if not success or not response:
        return []
        
    active_tasks = response.get('tasks', [])
    if isinstance(active_tasks, dict):
        return list(active_tasks.values())
        
    return active_tasks

def get_host_info(host_ids: List[int]) -> Dict[int, Dict[str, str]]:
    """
    Retrieves host information for a list of host IDs.
    Args:
        host_ids (List[int]): A list of host IDs to retrieve information for.
    Returns:
        Dict[int, Dict[str, str]]: A dictionary mapping host IDs to their details.
    """
    if not host_ids:
        return {}
        
    host_info = {}
    with db_session() as conn:
        cursor = conn.cursor(dictionary=True)
        format_strings = ','.join(['%s'] * len(host_ids))
        
        query = f"""
            SELECT h.host_id, h.host_name, r.room_name, m.mac_address
            FROM host_tracking h
            JOIN rooms r ON h.assigned_group_id = r.fog_group_id
            JOIN host_macs m ON h.host_id = m.host_id
            WHERE h.host_id IN ({format_strings})
        """
        cursor.execute(query, tuple(host_ids))
        
        for row in cursor.fetchall():
            host_id = row['host_id']
            if host_id not in host_info:
                host_info[host_id] = {
                    'name': row['host_name'],
                    'room': row['room_name'],
                    'mac': row['mac_address']
                }                
    return host_info

def process_failed_task(task_id: int, info: Dict[str, str]):
    """
    Processes a failed task and sends notifications.
    Args:
        task_id (int): The ID of the failed task.
        info (Dict[str, str]): The host information related to the task.
    """
    logging.warning(f"Task failure detected for {info['name']}.")
    mailer._send_email(
        f"[WARNING] Task Failure: {info['name']}",
        f"The task for host '{info['name']}' (MAC: {info['mac']}) in room '{info['room']}' has failed. The automation suite has cleared the task from the queue."
    )
    fog_api_request("DELETE", f"task/{task_id}")

def process_hung_task(task_id: int, info: Dict[str, str], duration_mins: int):
    """
    Processes a hung task and sends notifications.
    Args:
        task_id (int): The ID of the hung task.
        info (Dict[str, str]): The host information related to the task.
        duration_mins (int): The duration in minutes the task has been running.
    """
    logging.warning(f"Task timeout detected for {info['name']} ({duration_mins} mins).")
    mailer._send_email(
        f"[WARNING] Task Timeout: {info['name']}",
        f"The task for host '{info['name']}' (MAC: {info['mac']}) in room '{info['room']}' has been running for {duration_mins} minutes. It has been automatically cancelled."
    )
    fog_api_request("DELETE", f"task/{task_id}/cancel")

def check_task_states(timeout_minutes: int = 60):
    """
    Checks the states of active tasks and sends notifications for failures or timeouts.
    Args:
        timeout_minutes (int): The timeout duration in minutes for tasks. Defaults to 60 minutes.
    """
    try:
        active_tasks = get_active_tasks()
        if not active_tasks:
            return 
            
        active_host_ids = [int(str(t.get('hostID'))) for t in active_tasks if t.get('hostID')]
        host_info = get_host_info(active_host_ids)
        now = datetime.now()
        
        for task in active_tasks:
            host_id = int(task.get('hostID', 0))
            task_id = int(task.get('id', 0))
            state_id = int(task.get('stateID', 0))
            
            if host_id not in host_info:
                continue
                
            info = host_info[host_id]
            
            if state_id == 3:
                process_failed_task(task_id, info)
                continue

            start_time_str = task.get('createdTime', '')
            if start_time_str:
                try:
                    start_time = datetime.strptime(start_time_str, '%Y-%m-%d %H:%M:%S')
                    duration_mins = int((now - start_time).total_seconds() / 60)
                    
                    if duration_mins >= timeout_minutes:
                        process_hung_task(task_id, info, duration_mins)

                except ValueError:
                    logging.error(f"Could not parse task start time: '{start_time_str}'")

    except Exception as e:
        logging.error(f"Fatal error during task monitoring: {e}", exc_info=True)
        mailer._send_email(
            "[CRITICAL] Task Monitor Execution Failure",
            "The task monitoring script crashed unexpectedly. Check the logs for details.",
            priority="high"
        )

if __name__ == "__main__":
    check_task_states()