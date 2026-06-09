from dataclasses import dataclass
from datetime import datetime

@dataclass
class ScheduledCourse:
    """
    Represents a scheduled course.
    Args:
        room_id (str): The identifier of the room where the course is scheduled.
        end_time (datetime): The end time of the course.
    """
    room_id: str
    end_time: datetime
    
    @property
    def fog_deployment_time(self) -> datetime:
        """
        Returns the time when the fog deployment is scheduled.
        Returns:
            datetime: The fog deployment time, which is one hour after the course end time.
        """
        from datetime import timedelta
        return self.end_time + timedelta(hours=1)
    
    @property
    def db_time_format(self) -> str:
        """
        Returns the end time of the course in a format suitable for database storage.
        Returns:
            str: The end time formatted as 'YYYY-MM-DD HH:MM:SS'.
        """
        return self.end_time.strftime('%Y-%m-%d %H:%M:%S')