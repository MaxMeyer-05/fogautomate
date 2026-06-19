import requests
from typing import Dict, Any, Tuple, Optional

from config.config import FOG_API_URL, API_COURSE_END_TIME
from src.api.auth_manager import auth

from src.logger.logger import LogManager
logging = LogManager.get_logger("api_manager")

class ApiManager:
    """
    Singleton class to manage API requests for FOG and course APIs.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ApiManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.fog_session = requests.Session()
        self.course_session = requests.Session()
        self.fog_session.headers.update(auth.get_fog_headers())

    def execute_fog_request(self, method: str, endpoint: str, payload: Optional[Dict] = None) -> Tuple[bool, Any]:
        """
        Executes a request to the FOG API.
        Args:
            method (str): The HTTP method (GET, POST, etc.).
            endpoint (str): The API endpoint to call.
            payload (Optional[Dict]): The request payload for POST/PUT requests.
        Returns:
            Tuple[bool, Any]: A tuple containing a success flag and the response data.
        """
        url = f"{FOG_API_URL.rstrip('/')}/{endpoint.lstrip('/')}"
        
        try:
            response = self.fog_session.request(method, url, json=payload, timeout=15)
            response.raise_for_status()
            
            if not response.content:
                return True, {}
                
            return True, response.json()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"FOG API Exception [{method} {url}]: {e}")
            return False, None

    def fetch_courses(self, api_filters: Optional[Dict] = None) -> Tuple[bool, Any]:
        """
        Fetches courses from the course API.
        Args:
            api_filters (Optional[Dict]): Filters to apply to the API request.
        Returns:
            Tuple[bool, Any]: A tuple containing a success flag and the response data.
        """
        if not API_COURSE_END_TIME:
            logging.warning("API_COURSE_END_TIME is not configured.")
            return False, None

        try:
            response = self.course_session.get(API_COURSE_END_TIME, params=api_filters, timeout=15)
            response.raise_for_status()
            return True, response.json()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Course API Exception: {e}", exc_info=True)
            return False, None

api = ApiManager()