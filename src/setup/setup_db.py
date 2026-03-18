import sys
import json
from pathlib import Path

root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import ROOM_MAP_JSON, logging
from src.utils import db_session

def setup_database():
    """
    Set up the database schema and initial data.
    """
    print(">>> Setting up the database...")
    try:
        with db_session() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rooms (
                    room_name VARCHAR(255) NOT NULL,
                    ip_address VARCHAR(45) NOT NULL,
                    subnet_mask VARCHAR(45) NOT NULL,
                    fog_group_id INT NOT NULL,
                    PRIMARY KEY (room_name),
                    UNIQUE KEY (fog_group_id)
                ) ENGINE=InnoDB;
            """)

            cursor.execute("DROP TABLE IF EXISTS processed_courses;")
            cursor.execute("DROP TABLE IF EXISTS host_macs;")
            cursor.execute("DROP TABLE IF EXISTS host_tracking;")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_courses (
                    room_name VARCHAR(255) NOT NULL,
                    course_end_time DATETIME NOT NULL,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (room_name, course_end_time)
                ) ENGINE=InnoDB;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS host_tracking (
                    host_id INT NOT NULL,
                    host_name VARCHAR(255) NOT NULL,
                    last_ip VARCHAR(45) NOT NULL,
                    assigned_group_id INT NOT NULL,
                    PRIMARY KEY (host_id),
                    FOREIGN KEY (assigned_group_id) REFERENCES rooms(fog_group_id) ON DELETE CASCADE
                ) ENGINE=InnoDB;
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS host_macs (
                    mac_address VARCHAR(32) NOT NULL,
                    host_id INT NOT NULL,
                    PRIMARY KEY (mac_address),
                    FOREIGN KEY (host_id) REFERENCES host_tracking(host_id) ON DELETE CASCADE
                ) ENGINE=InnoDB;
            """)

            if ROOM_MAP_JSON.exists():
                with open(ROOM_MAP_JSON, 'r') as f:
                    data = json.load(f).get("HH", [])
                    
                    entries = [
                        (item['room'], item['ip'], item['mask'], item['fog_group_id']) 
                        for item in data
                    ]
                    
                    query = """
                        INSERT INTO rooms (room_name, ip_address, subnet_mask, fog_group_id) 
                        VALUES (%s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE 
                            ip_address=VALUES(ip_address), 
                            subnet_mask=VALUES(subnet_mask), 
                            fog_group_id=VALUES(fog_group_id)
                    """
                    cursor.executemany(query, entries)
                    logging.info(f"Master Data Setup: {len(entries)} rooms synced to MariaDB.")

            conn.commit()
            print(">>> Database Setup complete. Database ready for automation.")
            
    except Exception as e:
        logging.error(f"Fatal error during database setup: {e}", exc_info=True)
        print(f">>> Error: Database setup failed. Check logs for details.")

if __name__ == "__main__":
    setup_database()