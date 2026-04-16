from datetime import datetime
from typing import Callable, List, Optional

import src.notifications.mailer as mailer
from jobs.monitoring.check_storage import check_image_partition
from jobs.monitoring.monitor_tasks import check_task_states
from jobs.auto_register import process_new_hosts, cleanup_stale_hosts
from jobs.auto_scheduler import run_scheduler
from jobs.auto_wake import run_wake_cycle
from config.config import logging

def run_scheduled_task(
    task_func: Callable,
    task_name: str,
    allowed_weekdays: List[int] = [0, 1, 2, 3, 4],  # Default to Monday-Friday
    allowed_hours: Optional[List[int]] = None,
    minute_interval: Optional[int] = None,
    exact_minute: Optional[int] = None
    ):
    """
    Runs a scheduled task based on the current time and specified conditions.
    Args:
        task_func (Callable): The function to execute for the task.
        task_name (str): A descriptive name for the task, used in logging and notifications.
        allowed_weekdays (List[int]): List of allowed weekdays (0=Monday, 6=Sunday). Default is Monday-Friday.
        allowed_hours (Optional[List[int]]): List of allowed hours (0-23). If None, runs every hour.
        minute_interval (Optional[int]): If set, runs at intervals of this many minutes (e.g., 15 for :00, :15, :30, :45).
        exact_minute (Optional[int]): If set, runs only at this exact minute of the hour (0-59).
    """
    now = datetime.now()

    if now.weekday() not in allowed_weekdays:
        return
    
    if allowed_hours is not None and now.hour not in allowed_hours:
        return
    
    should_run = False
    if exact_minute is not None and now.minute == exact_minute:
        should_run = True
    elif minute_interval is not None and now.minute % minute_interval == 0:
        should_run = True

    if should_run:
        try:
            task_func()
        except Exception as e:
            logging.error(f"Error in {task_name}: {e}", exc_info=True)
            mailer._send_email(f"[CRITICAL] {task_name} Failed", f"Error:\n\n{e}", priority="high")

def auto_register_wrapper():
    """
    Wrapper function to run both auto-register tasks sequentially.
    """
    process_new_hosts()
    cleanup_stale_hosts()


def main():
    """
    Main entry point for the program. Schedules and runs various tasks based on defined intervals and conditions.
    """
    # Define standard working hours (07:00 through 18:59)
    working_hours = list(range(7, 19))
    
    run_scheduled_task(
        task_func=auto_register_wrapper,
        task_name="Auto-Register",
        allowed_hours=working_hours,
        minute_interval=15  # Runs at :00, :15, :30, :45
    )

    run_scheduled_task(
        task_func=run_scheduler,
        task_name="Auto-Scheduler",
        allowed_hours=working_hours,
        exact_minute=0      # Runs exactly at the top of the hour
    )

    run_scheduled_task(
        task_func=run_wake_cycle,
        task_name="Auto-Wake",
        allowed_hours=working_hours,
        minute_interval=5   # Runs every 5 minutes
    )

    run_scheduled_task(
        task_func=check_task_states,
        task_name="Task Monitoring",
        allowed_hours=working_hours,
        exact_minute=30     # Runs exactly at the bottom of the hour
    )

    run_scheduled_task(
        task_func=check_image_partition,
        task_name="Storage Health Check",
        allowed_hours=[8, 20], # Runs only during the 8th and 20th hours
        exact_minute=0         # Runs exactly at 08:00 and 20:00
    )


if __name__ == "__main__":
    main()