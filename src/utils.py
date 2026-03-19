import sys
import base64
import requests
import mysql.connector
from contextlib import contextmanager
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from pathlib import Path
from typing import Tuple, Dict, Optional, Any

root_path = Path(__file__).resolve().parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import FOG_DB_CONFIG, FOG_API_URL, logging

@contextmanager
def db_session():
    """
    Context manager for database sessions.
    Yields a MySQL connection object and ensures proper cleanup.
    """
    conn = None
    try:
        conn = mysql.connector.connect(**FOG_DB_CONFIG)
        yield conn
    except mysql.connector.Error as e:
        logging.error(f"Database Critical Failure: {e}", exc_info=True)
        if conn:
            conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_fog_tokens() -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch FOG API tokens from the database and encode them in base64.
    Returns:
        Tuple[Optional[str], Optional[str]]: A tuple containing the server token and user token.
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT settingValue FROM fog.globalSettings WHERE settingKey='FOG_API_TOKEN'")
            server_token = base64.b64encode(cursor.fetchone()['settingValue'].encode('utf-8')).decode('utf-8')

            cursor.execute("SELECT uAPIToken FROM fog.users WHERE uName='fog'")
            user_token = base64.b64encode(cursor.fetchone()['uAPIToken'].encode('utf-8')).decode('utf-8')

            return server_token, user_token
    except Exception as e:
        logging.error(f"Failed to fetch FOG tokens from DB.", exc_info=True)
        return None, None

def get_api_session() -> requests.Session:
    """
    Create and configure a requests session with retry strategy.
    Returns:
        requests.Session: Configured requests session.
    """
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def fog_api_request(method: str, endpoint: str, payload: Optional[Dict[Any, Any]] = None, timeout: int = 15) -> Tuple[bool, Any]:
    """
    Make a request to the FOG API with the given method, endpoint, and payload.
    Args:
        method (str): The HTTP method to use (e.g., "GET", "POST").
        endpoint (str): The API endpoint to target (e.g., "task/active").
        payload (Optional[Dict[Any, Any]]): The JSON payload to send with the request.
        timeout (int): The request timeout in seconds.
    Returns:
        Tuple[bool, Any]: A tuple containing a success flag and the response data.
    """
    server_token, user_token = get_fog_tokens()
    if not server_token or not user_token:
        logging.error("API Request aborted: Could not generate FOG tokens.")
        return False, None
        
    headers = {
        'fog-api-token': server_token,
        'fog-user-token': user_token,
        'Content-Type': 'application/json'
    }
    
    url = f"{FOG_API_URL}/{endpoint.lstrip('/')}"
    session = get_api_session()
    
    try:
        response = session.request(method, url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        
        if response.text:
            return True, response.json()
        return True, None
        
    except requests.exceptions.RequestException as e:
        logging.error(f"FOG API '{method}' to '{endpoint}' failed: {e}", exc_info=True)
        return False, None