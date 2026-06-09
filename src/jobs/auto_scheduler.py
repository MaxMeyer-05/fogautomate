from datetime import datetime, timedelta

from config.config import GERMAN_TZ, FOG_TASK_TYPE
from src.data.db_manager import db
from src.api.api_manager import api
import src.notifications.mailer as mailer
from src.services.course_service import CourseService

from src.logger.logger import LogManager
logging = LogManager.get_logger("auto_scheduler")

def run_scheduler():
    """
    Executes the scheduling process for active courses.
    """
    now = datetime.now(GERMAN_TZ)
    cutoff_date = now - timedelta(hours=2)
    max_planning_date = now + timedelta(hours=24)
    
    course_service = CourseService()

    try:
        with db.get_connection() as conn:
            cursor = conn.cursor(dictionary=True)
            
            cursor.execute("DELETE FROM processed_courses WHERE course_end_time < DATE_SUB(NOW(), INTERVAL 14 DAY)")
            conn.commit()

            cursor.execute("SELECT room_name, fog_group_id FROM rooms")
            valid_rooms = {row['room_name']: row['fog_group_id'] for row in cursor.fetchall()}

            courses = course_service.fetch_active_courses()

            for course in courses:
                if course.room_id not in valid_rooms or course.end_time < cutoff_date:
                    continue
                if course.fog_deployment_time > max_planning_date:
                    continue

                cursor.execute(
                    "SELECT 1 FROM processed_courses WHERE room_name = %s AND course_end_time = %s",
                    (course.room_id, course.db_time_format)
                )
                if cursor.fetchone() is not None:
                    continue

                deployment_time = course.fog_deployment_time
                if deployment_time < now:
                    deployment_time = now + timedelta(minutes=5)

                schedule_time_str = deployment_time.strftime('%Y-%m-%d %H:%M:%S')
                fog_group_id = valid_rooms[course.room_id]

                payload = {
                    "taskTypeID": FOG_TASK_TYPE,
                    "taskName": f"AutoDeploy_{course.room_id}",
                    "scheduleTime": schedule_time_str 
                }
                success, _ = api.execute_fog_request("POST", f"group/{fog_group_id}/task", payload)

                if success:
                    logging.info(f"API SUCCESS: Scheduled '{course.room_id}' at {schedule_time_str}.")
                    cursor.execute(
                        "INSERT INTO processed_courses (room_name, course_end_time) VALUES (%s, %s)",
                        (course.room_id, course.db_time_format)
                    )
                    conn.commit()

    except Exception as e:
        logging.error(f"Fatal Scheduler execution error.", exc_info=True)
        mailer._send_email("[CRITICAL] FOG Scheduler Failure", f"Error:\n\n{e}", priority="high")

if __name__ == "__main__":
    run_scheduler()