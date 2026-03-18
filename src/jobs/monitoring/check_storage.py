import shutil
import sys
from pathlib import Path

root_path = Path(__file__).resolve().parent.parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import logging
import src.notifications.mailer as mailer

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

        if percent_used > threshold_percent:
            logging.warning(f"Disk usage on '{partition_path}' is at {percent_used:.2f}% (Free: {free_gb:.2f} GB).")
            mailer._send_email(
                f"[CRITICAL] Disk Usage Alert: {partition_path}",
                f"Disk usage on '{partition_path}' is at {percent_used:.2f}% (Free: {free_gb:.2f} GB).",
                priority="high"
            )
        else:
            logging.info(f"Disk usage on '{partition_path}' is at {percent_used:.2f}% (Free: {free_gb:.2f} GB).")
    except FileNotFoundError:
        logging.error(f"Partition '{partition_path}' not found.", exc_info=True)
        mailer._send_email(
            f"[CRITICAL] Storage Monitor Failure",
            f"The FOG image partition '{partition_path}' was not found.",
            priority="high"
        )
    except Exception as e:
        logging.error(f"Error checking disk usage for '{partition_path}': {e}", exc_info=True)
        mailer._send_email(
            f"[CRITICAL] Storage Monitor Crash",
            f"The storage monitoring script crashed. Check the logs for details.",
            priority="high"
        )

if __name__ == "__main__":
    check_image_partition()