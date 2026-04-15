import os
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import timedelta, timezone
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

LOG_DIR = BASE_DIR / "logs"
DATA_TEMP_DIR = BASE_DIR / "data" / "temp"
DATA_MAP_DIR = BASE_DIR / "data" / "mappings"

for directory in [LOG_DIR, DATA_TEMP_DIR, DATA_MAP_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

ROOM_MAP_JSON = DATA_MAP_DIR / "room-map.json"

GERMAN_TZ = timezone(timedelta(hours=1))

FOG_DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'), 
    'user': os.getenv('DB_USER', 'fog'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'fog_automation'),
    'autocommit': True
}

FOG_API_URL = os.getenv('FOG_API_URL', 'http://127.0.0.1/fog')
FOG_TASK_TYPE = int(os.getenv('FOG_TASK_TYPE', '8'))

SMTP_HOST = os.getenv('SMTP_HOST', '127.0.0.1')
SENDER_EMAIL = os.getenv('SENDER_EMAIL', 'fog@localhost')

raw_emails = os.getenv('ADMIN_EMAILS', '')
ADMIN_EMAILS = [email.strip() for email in raw_emails.split(',')] if raw_emails else []

API_COURSE_END_TIME = os.getenv('API_COURSE_END_TIME', 'https://www.placeholder.de/api/courses')

logger = logging.getLogger()
if logger.hasHandlers():
    logger.handlers.clear()
    
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s] - %(message)s')

class InfoFilter(logging.Filter):
    def filter(self, record):
        return record.levelno == logging.INFO

activity_handler = TimedRotatingFileHandler(
    filename=LOG_DIR / "activity.log",
    when="midnight", interval=1, backupCount=60, encoding="utf-8"
)
activity_handler.setLevel(logging.INFO)
activity_handler.setFormatter(formatter)
activity_handler.addFilter(InfoFilter())

error_handler = TimedRotatingFileHandler(
    filename=LOG_DIR / "error.log",
    when="midnight", interval=1, backupCount=60, encoding="utf-8"
)
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(formatter)

logger.addHandler(activity_handler)
logger.addHandler(error_handler)