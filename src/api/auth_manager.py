import os
from typing import Dict

from src.logger.logger import LogManager
logging = LogManager.get_logger("auth_manager")

class AuthManager:
    """
    Singleton class to manage authentication tokens for FOG API.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AuthManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self._fog_user_token = os.getenv('FOG_USER_TOKEN', '').strip()
        self._fog_api_token = os.getenv('FOG_API_TOKEN', '').strip()

        if not self._fog_user_token or not self._fog_api_token:
            logging.warning("AuthManager: FOG API tokens are missing or incomplete in the .env file!")

    def get_fog_headers(self) -> Dict[str, str]:
        """
        Returns the headers required for FOG API requests.
        """
        return {
            "Content-Type": "application/json",
            "fog-user-token": self._fog_user_token,
            "fog-api-token": self._fog_api_token
        }
    
auth = AuthManager()