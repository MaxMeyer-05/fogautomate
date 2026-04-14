import time
from datetime import datetime
from jobs.monitoring.check_storage import check_image_partition
from jobs.monitoring.monitor_tasks import check_task_states
from jobs.auto_register import process_new_hosts, cleanup_stale_hosts
from jobs.auto_scheduler import run_scheduler
from jobs.auto_wake import run_wake_cycle
import src.notifications.mailer as mailer
from config.config import logging

def main():
    now = datetime.now()
            
    is_weekday = now.weekday() < 5
    is_working_hours = 7 <= now.hour < 19
    m = now.minute
    h = now.hour

    # 1. Auto-Wake: Runs every 5 minutes (e.g., :00, :05, :10)
    if is_weekday and is_working_hours and m % 5 == 0:
        try:
            run_wake_cycle()
        except Exception as e:
            logging.error(f"Error in Auto-Wake: {e}", exc_info=True)
            mailer._send_email("[CRITICAL] Auto-Wake Failed", f"Error:\n\n{e}", priority="high")

    # 2. Auto-Register: Runs every 15 minutes (e.g., :00, :15, :30)
    if is_weekday and is_working_hours and m % 15 == 0:
        try:
            process_new_hosts()
            cleanup_stale_hosts()
        except Exception as e:
            logging.error(f"Error in Auto-Register: {e}", exc_info=True)
            mailer._send_email("[CRITICAL] Auto-Register Failed", f"Error:\n\n{e}", priority="high")
        
    # 3. Auto-Scheduler: Runs at the top of the hour (:00)
    if is_weekday and is_working_hours and m == 0:
        try:
            run_scheduler()
        except Exception as e:
            logging.error(f"Error in Auto-Scheduler: {e}", exc_info=True)
            mailer._send_email("[CRITICAL] Auto-Scheduler Failed", f"Error:\n\n{e}", priority="high")

    # 4. Task Monitoring: Runs at the bottom of the hour (:30)
    if is_weekday and is_working_hours and m == 30:
        try:
            check_task_states()
        except Exception as e:
            logging.error(f"Error in Task Monitoring: {e}", exc_info=True)
            mailer._send_email("[CRITICAL] Task Monitoring Failed", f"Error:\n\n{e}", priority="high")

    # 5. Storage Check: Runs twice a day (08:00 and 20:00)
    if h in [8, 20] and m == 0:
        try:
            check_image_partition()
        except Exception as e:
            logging.error(f"Error in Storage Check: {e}", exc_info=True)
            mailer._send_email("[CRITICAL] Storage Check Failed", f"Error:\n\n{e}", priority="high")


if __name__ == "__main__":
    main()