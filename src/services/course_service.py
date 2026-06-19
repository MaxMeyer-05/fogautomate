from typing import List
from datetime import datetime

from src.api.api_manager import api
from src.models.course import ScheduledCourse
from config.config import GERMAN_TZ

from src.logger.logger import LogManager
logging = LogManager.get_logger("course_service")

class CourseService:
    
    def __init__(self):
        self.valid_facility_range = range(1, 9)

    def fetch_active_courses(self) -> List[ScheduledCourse]:
        """
        Fetches active courses from the API, filters and maps them to ScheduledCourse objects.
        Retruns:
            List[ScheduledCourse]: A list of valid ScheduledCourse objects.
        """
        api_filters = {'facilityid': '1,2,3,4,5,6,7,8'}
        success, json_response = api.fetch_courses(api_filters)
        
        if not success or not json_response:
            return []

        courses: List[ScheduledCourse] = []
        course_list = json_response.get('data', [])

        if not isinstance(course_list, list):
            return courses

        for item in course_list:
            course = self._parse_course_item(item)
            if course:
                courses.append(course)

        logging.info(f"CourseService: Successfully mapped {len(courses)} valid courses.")
        return courses

    def _parse_course_item(self, item: dict) -> ScheduledCourse | None:
        """
        Parses a single course item from the API response and validates it.
        Args:
            item (dict): A dictionary representing a course item from the API response.
        Returns:
            ScheduledCourse | None: A ScheduledCourse object if valid, otherwise None.
        """
        raw_facility_id = item.get('facilityid')
        
        try:
            facility_id = int(str(raw_facility_id).strip())
            if facility_id not in self.valid_facility_range:
                return None
        except (ValueError, TypeError):
            return None
            
        room = str(facility_id)
        end_date = str(item.get('end', '')).strip()
        end_time = str(item.get('endtime', '')).strip()
        
        if not (room and end_date and end_time):
            return None

        full_time_str = f"{end_date}T{end_time}".replace('Z', '+00:00')
        try:
            dt_obj = datetime.fromisoformat(full_time_str).astimezone(GERMAN_TZ)
            return ScheduledCourse(room_id=room, end_time=dt_obj)
        except ValueError:
            logging.warning(f"CourseService: Invalid time format for room {room}.")
            return None