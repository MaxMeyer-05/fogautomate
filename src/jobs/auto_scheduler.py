import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import API_COURSE_END_TIME, GERMAN_TZ, FOG_TASK_TYPE, logging
from src.utils import db_session, fog_api_request
import src.notifications.mailer as mailer

def clean_old_records(cursor, conn):
    """
    Remove records from 'processed_courses' that are older than 14 days to prevent database bloat.
    Args:
        cursor: The database cursor.
        conn: The database connection.
    """
    cursor.execute("DELETE FROM processed_courses WHERE course_end_time < DATE_SUB(NOW(), INTERVAL 14 DAY)")
    if cursor.rowcount > 0:
        logging.info(f"CLEANUP: Removed {cursor.rowcount} records older than 14 days.")
    conn.commit()

def get_valid_rooms(cursor) -> Dict[str, int]:
    """
    Fetches valid rooms and their corresponding FOG group IDs.
    Args:
        cursor: The database cursor.
    Returns:
        Dict[str, int]: A dictionary mapping room names to FOG group IDs.
    """
    cursor.execute("SELECT room_name, fog_group_id FROM rooms")
    return {row['room_name']: row['fog_group_id'] for row in cursor.fetchall()}

def get_scheduled_courses() -> List[Tuple[str, str]]:
    """
    Fetches scheduled courses from the SQLite database.
    Returns:
        List[Tuple[str, str]]: A list of tuples containing room names and end times.
    """
    if not API_COURSE_END_TIME:
        logging.warning("API_COURSE_END_TIME is not configured in .env.")
        return []
        
    try:
        response = requests.get(API_COURSE_END_TIME, timeout=15)
        response.raise_for_status()
        json_response = response.json()
        
        courses = []
        course_list = json_response.get('data', [])
        
        if isinstance(course_list, list):
            for item in course_list:
                raw_facility_id = item.get('facilityid')
                
                try:
                    facility_id = int(str(raw_facility_id).strip())
                    if not (1 <= facility_id <= 8):
                        continue
                except (ValueError, TypeError):
                    continue
                    
                room = str(facility_id)
                end_date = str(item.get('end', '')).strip()
                end_time = str(item.get('endtime', '')).strip()
                
                if room and end_date and end_time:
                    full_end_time_str = f"{end_date}T{end_time}"
                    courses.append((room, full_end_time_str))
                    
        return courses
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch course schedule from API: {e}", exc_info=True)
        return []

def is_course_processed(cursor, room_name: str, db_course_time: str) -> bool:
    """
    Checks if a course has already been processed.
    Args:
        cursor: The database cursor.
        room_name (str): The name of the room.
        db_course_time (str): The end time of the course in the database format.
    Returns:
        bool: True if the course has been processed, False otherwise.
    """
    cursor.execute(
        "SELECT 1 FROM processed_courses WHERE room_name = %s AND course_end_time = %s",
        (room_name, db_course_time)
    )
    return cursor.fetchone() is not None

def mark_course_processed(cursor, conn, room_name: str, db_course_time: str):
    """
    Marks a course as processed by inserting a record into the 'processed_courses' table.
    Args:
        cursor: The database cursor.
        conn: The database connection.
        room_name (str): The name of the room.
        db_course_time (str): The end time of the course in the database format.
    """
    cursor.execute(
        "INSERT INTO processed_courses (room_name, course_end_time) VALUES (%s, %s)",
        (room_name, db_course_time)
    )
    conn.commit()

def schedule_fog_deployment(fog_group_id: int, room_name: str, schedule_time_str: str) -> bool:
    """
    Schedules a FOG deployment for a specific room at a given time.
    Args:
        fog_group_id (int): The FOG group ID of the room.
        room_name (str): The name of the room.
        schedule_time_str (str): The scheduled time for the deployment in string format.
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

def process_course_deployments(cursor, conn, valid_rooms: Dict[str, int], courses: List[Tuple[str, str]]):
    """
    Processes course deployments by scheduling FOG tasks for valid rooms.
    Args:
        cursor: The database cursor.
        conn: The database connection.
        valid_rooms (Dict[str, int]): A dictionary mapping room names to FOG group IDs.
        courses (List[Tuple[str, str]]): A list of tuples containing room names and course end times.
    """
    now = datetime.now(GERMAN_TZ)
    cutoff_date = now - timedelta(hours=2)
    max_planning_date = now + timedelta(hours=24)

    for room_name, end_time_str in courses:
        clean_time = end_time_str.replace('Z', '+00:00')
        course_end_dt = datetime.fromisoformat(clean_time).astimezone(GERMAN_TZ)
        db_course_time = course_end_dt.strftime('%Y-%m-%d %H:%M:%S')

        # Skip if not mapped or if course ended too long ago
        if room_name not in valid_rooms or course_end_dt < cutoff_date:
            continue

        deployment_time = course_end_dt + timedelta(hours=1)
        if deployment_time > max_planning_date:
            continue

        if not is_course_processed(cursor, room_name, db_course_time):
            # If the calculated deployment time passed while the script was inactive, start immediately (+5m)
            if deployment_time < now:
                deployment_time = now + timedelta(minutes=5)

            schedule_time_str = deployment_time.strftime('%Y-%m-%d %H:%M:%S')
            
            if schedule_fog_deployment(valid_rooms[room_name], room_name, schedule_time_str):
                mark_course_processed(cursor, conn, room_name, db_course_time)

def run_scheduler():
    """
    Main execution function for the FOG Scheduler job.
    """
    try:
        with db_session() as maria_conn:
            maria_cursor = maria_conn.cursor(dictionary=True)
            
            clean_old_records(maria_cursor, maria_conn)
            valid_rooms = get_valid_rooms(maria_cursor)
            courses = get_scheduled_courses()
            
            if courses and valid_rooms:
                process_course_deployments(maria_cursor, maria_conn, valid_rooms, courses)

    except Exception as e:
        logging.error(f"Fatal Scheduler execution error.", exc_info=True)
        mailer._send_email(
            "[CRITICAL] FOG Scheduler Failure",
            f"An error occurred during the execution of the FOG deployment scheduler.\n\nError: {e}\n\nPlease check the logs for details.",
            priority="high"
        )