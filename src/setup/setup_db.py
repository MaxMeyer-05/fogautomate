import os
import sys
import json
import subprocess
from pathlib import Path

root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import ROOM_MAP_JSON, FOG_DB_CONFIG, logging
from src.utils import db_session

def create_database():
    """
    Create the database if it doesn't exist.
    """
    db_name = FOG_DB_CONFIG.get('database')
    db_user = FOG_DB_CONFIG.get('user')
    db_password = FOG_DB_CONFIG.get('password')
    
    sql_commands = f"""
    CREATE DATABASE IF NOT EXISTS `{db_name}`;
    CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{db_password}';
    GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'localhost';
    GRANT ALL PRIVILEGES ON fog.* TO '{db_user}'@'localhost';
    FLUSH PRIVILEGES;
    """
    
    try:
        print(f">>> Provisioning database '{db_name}' and user '{db_user}'...")
        
        result = subprocess.run(
            ["mysql", "-u", "root", "-e", sql_commands],
            check=True,
            stderr=subprocess.PIPE,
            text=True
        )
        print(f">>> Database '{db_name}' provisioned successfully.")
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if e.stderr else str(e)
        logging.error(f"Failed to provision database via mysql CLI: {error_msg}")
        print(f">>> CRITICAL ERROR: Could not provision database. Check logs for details.")
        sys.exit(1)
    except FileNotFoundError:
        print(">>> CRITICAL ERROR: 'mysql' command not found. Is MariaDB installed?")
        sys.exit(1)

def setup_database():
    """
    Set up the database schema and initial data.
    """
    print(">>> Setting up the database schema...")
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
            print(">>> Database Setup complete. Ready for automation.")
            
    except Exception as e:
        logging.error("Fatal error during database setup.", exc_info=True)
        print(f">>> Error: Database setup failed. Check logs for details.")

if __name__ == "__main__":
    if os.geteuid() != 0: # Check if the script is run as root (getuid() only exists on Linux and Unix systems)
        print(">>> ERROR: This setup script must be run as root (sudo).")
        sys.exit(1)
        
    create_database()
    setup_database()