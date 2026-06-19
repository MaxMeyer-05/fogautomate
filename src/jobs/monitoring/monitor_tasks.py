import src.notifications.mailer as mailer
from src.services.task_service import TaskService
from src.services.host_service import HostService

from src.logger.logger import LogManager
logging = LogManager.get_logger("monitor_tasks")

def check_task_states(timeout_minutes: int = 60):
    """
    Monitors the state of active tasks and takes appropriate actions for failures or timeouts.
    Args:
        timeout_minutes (int): The duration in minutes after which a task is considered hung.
    """
    task_service = TaskService()
    host_service = HostService()
    
    try:
        active_tasks = task_service.fetch_active_tasks()
        if not active_tasks:
            return 
            
        host_ids = [t.host_id for t in active_tasks]
        host_info = host_service.get_host_info_by_ids(host_ids)
        
        for task in active_tasks:
            if task.host_id not in host_info:
                continue
                
            info = host_info[task.host_id]
            first_mac = info['macs'][0] if info['macs'] else "UNKNOWN"
            
            if task.state_id == 3:
                logging.warning(f"Task failure detected for {info['name']}.")
                mailer._send_email(
                    f"[WARNING] Task Failure: {info['name']}",
                    f"The task for host '{info['name']}' (MAC: {first_mac}) in room '{info['room']}' has failed. Clearing queue."
                )
                task_service.clear_failed_task(task.id)
                continue

            if task.duration_minutes >= timeout_minutes:
                logging.warning(f"Task timeout detected for {info['name']} ({task.duration_minutes} mins).")
                mailer._send_email(
                    f"[WARNING] Task Timeout: {info['name']}",
                    f"The task for host '{info['name']}' (MAC: {first_mac}) in room '{info['room']}' has been running for {task.duration_minutes} minutes. Cancelling."
                )
                task_service.cancel_hung_task(task.id)

    except Exception as e:
        logging.error(f"Fatal error during task monitoring: {e}", exc_info=True)
        mailer._send_email("[CRITICAL] Task Monitor Execution Failure", "Error during task state check.", priority="high")

if __name__ == "__main__":
    check_task_states()