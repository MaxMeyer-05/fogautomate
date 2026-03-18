import sys
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import DATABASE_FILE, GERMAN_TZ, FOG_TASK_TYPE, logging
from src.utils import db_session, fog_api_request
import src.notifications.mailer as mailer

def schedule_fog_deployment(fog_group_id: int, room_name: str, schedule_time_str: str) -> bool:
    """
    Schedule a FOG deployment task via the API.
    Args:
        fog_group_id (int): The ID of the FOG group to deploy to.
        room_name (str): The name of the room to deploy to.
        schedule_time_str (str): The scheduled time for the deployment in the format 'YYYY-MM-DD HH:MM:SS'.
    Returns:
        bool: True if the deployment was successfully scheduled, False otherwise.
    """
    payload = {
        "taskTypeID": FOG_TASK_TYPE,
        "taskName": f"AutoDeploy_{room_name}",
        "scheduleTime": schedule_time_str 
    }
    success, _ = fog_api_request("POST", f"group/{fog_group_id}/task", payload)
    if success:
        logging.info(f"API SUCCESS: FOG scheduled to image '{room_name}' at {schedule_time_str}.")
    return success

def clean_old_records(cursor, conn):
    """
    Clean up old records from the processed_courses table.
    Args:
        cursor: The database cursor.
        conn: The database connection.
    """
    cursor.execute("DELETE FROM processed_courses WHERE course_end_time < DATE_SUB(NOW(), INTERVAL 14 DAY)")
    if cursor.rowcount > 0:
        logging.info(f"CLEANUP: Removed {cursor.rowcount} records older than 14 days.")
    conn.commit()

def run_scheduler():
    """
    Run the FOG deployment scheduler.
    """
    now = datetime.now(GERMAN_TZ)
    cutoff_date = now - timedelta(hours=2)
    max_planning_date = now + timedelta(hours=24)
    
    try:
        with db_session() as maria_conn:
            maria_cursor = maria_conn.cursor(dictionary=True)
            clean_old_records(maria_cursor, maria_conn)

            maria_cursor.execute("SELECT room_name, fog_group_id FROM rooms")
            valid_rooms = {row['room_name']: row['fog_group_id'] for row in maria_cursor.fetchall()}

            # Fetch course schedules from the temporary SQLite database
            with sqlite3.connect(DATABASE_FILE) as sqlite_conn:
                sqlite_cursor = sqlite_conn.cursor()
                sqlite_cursor.execute("SELECT room_name, end_time FROM courses_schedule")
                
                for room_name, end_time_str in sqlite_cursor.fetchall():
                    clean_time = end_time_str.replace('Z', '+00:00')
                    course_end_dt = datetime.fromisoformat(clean_time).astimezone(GERMAN_TZ)
                    db_course_time = course_end_dt.strftime('%Y-%m-%d %H:%M:%S')

                    if room_name not in valid_rooms or course_end_dt < cutoff_date:
                        continue

                    deployment_time = course_end_dt + timedelta(hours=1)
                    if deployment_time > max_planning_date:
                        continue

                    maria_cursor.execute(
                        "SELECT 1 FROM processed_courses WHERE room_name = %s AND course_end_time = %s",
                        (room_name, db_course_time)
                    )
                    
                    if not maria_cursor.fetchone():
                        if deployment_time < now:
                            deployment_time = now + timedelta(minutes=5)

                        schedule_time_str = deployment_time.strftime('%Y-%m-%d %H:%M:%S')
                        if schedule_fog_deployment(valid_rooms[room_name], room_name, schedule_time_str):
                            maria_cursor.execute(
                                "INSERT INTO processed_courses (room_name, course_end_time) VALUES (%s, %s)",
                                (room_name, db_course_time)
                            )
                            maria_conn.commit()
    except Exception as e:
        logging.error(f"Fatal Scheduler execution error.", exc_info=True)
        mailer._send_email(
            "[CRITICAL] FOG Scheduler Failure",
            f"An error occurred during the execution of the FOG deployment scheduler.\n\nError: {e}\n\nPlease check the logs for details.",
            priority="high"
        )

if __name__ == "__main__":
    run_scheduler()