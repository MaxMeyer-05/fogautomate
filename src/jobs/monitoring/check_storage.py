import shutil

import src.notifications.mailer as mailer

from src.logger.logger import LogManager
logging = LogManager.get_logger("check_storage")

def check_image_partition(threshold_percent: float = 85.0):
    """
    Check the disk usage of the image partition and send an alert if it exceeds the threshold.
    Args:
        threshold_percent (float): The disk usage percentage threshold to trigger an alert.
    """
    partition_path = "/images"
    
    try:
        total, used, free = shutil.disk_usage(partition_path)
        
        percent_used = (used / total) * 100
        free_gb = free / (1024 ** 3)
        
        if percent_used >= threshold_percent:
            logging.warning(f"CRITICAL STORAGE ALERT: {partition_path} is {percent_used:.1f}% full. Only {free_gb:.1f} GB free.")
            mailer._send_email(
                f"[CRITICAL] Disk Usage Alert: {partition_path}",
                f"Disk usage on '{partition_path}' is at {percent_used:.2f}% (Free: {free_gb:.2f} GB).\n\nPlease clean up old FOG images immediately.",
                priority="high"
            )
        else:
            logging.info(f"Storage healthy: {partition_path} is at {percent_used:.1f}% capacity ({round(free_gb, 1)} GB free).")
            
    except FileNotFoundError:
        logging.error(f"Storage check failed: The path '{partition_path}' does not exist or is not mounted.", exc_info=True)
        mailer._send_email(
            f"[CRITICAL] Storage Monitor Failure",
            f"The FOG image partition '{partition_path}' was not found. Has the drive been unmounted?",
            priority="high"
        )
    except Exception as e:
        logging.error(f"Fatal error while checking storage space for {partition_path}.", exc_info=True)
        mailer._send_email(
            f"[CRITICAL] Storage Monitor Crash",
            f"The storage monitoring script crashed.\n\nError: {e}",
            priority="high"
        )
