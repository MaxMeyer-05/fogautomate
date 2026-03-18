import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import timedelta, timezone

GERMAN_TZ = timezone(timedelta(hours=1))

BASE_DIR = Path(__file__).resolve().parent.parent

LOG_DIR = BASE_DIR / "logs"
DATA_TEMP_DIR = BASE_DIR / "data" / "temp"
DATA_MAP_DIR = BASE_DIR / "data" / "mappings"

for directory in [LOG_DIR, DATA_TEMP_DIR, DATA_MAP_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

DATABASE_FILE = DATA_TEMP_DIR / "courses.db"
ROOM_MAP_JSON = DATA_MAP_DIR / "room-map.json"

FOG_DB_CONFIG = {
    'host': 'localhost', 
    'user': 'fog',
    'password': '1234',
    'database': 'fog_automation',
    'autocommit': True
}

FOG_API_URL = "http://localhost/fog"
FOG_TASK_TYPE = 8

SMTP_HOST = "smtp.domain.com"           # Replace with actual SMTP server address
ADMIN_EMAILS = ["admin@domain.com"]     # Replace with actual admin email addresses
SENDER_EMAIL = "fog-server@domain.com"  # Replace with actual sender email address

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
    when="midnight",
    interval=1,
    backupCount=60,
    encoding="utf-8"
)
activity_handler.setLevel(logging.INFO)
activity_handler.setFormatter(formatter)
activity_handler.addFilter(InfoFilter())

error_handler = TimedRotatingFileHandler(
    filename=LOG_DIR / "error.log",
    when="midnight",
    interval=1,
    backupCount=60,
    encoding="utf-8"
)
error_handler.setLevel(logging.WARNING)
error_handler.setFormatter(formatter)

logger.addHandler(activity_handler)
logger.addHandler(error_handler)