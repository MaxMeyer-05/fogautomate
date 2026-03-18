# FOG Server Automation Suite

This project is a complete, state-aware Python automation pipeline built on top of the open-source FOG Project. It provides zero-touch PC registration, intelligent Wake-on-LAN (WoL) routing, course-based imaging scheduling, and comprehensive system observability via email alerts.

## Features
* **Auto-Registration:** Automatically detects new PCs, links them to their physical room based on their IP subnet, and registers all active MAC addresses to prevent duplicate ghost entries.
* **State-Aware Wake-on-LAN:** Detects active FOG deployments and selectively blasts WoL magic packets to every known MAC address of the target PCs. Includes granular success/failure parsing to detect unplugged hardware.
* **Storage Monitoring:** Actively monitors the server's `/images` partition and triggers alerts before the drive fills up.
* **Email Digest System:** Buffers errors and alerts to prevent inbox spam, delivering consolidated, categorized notifications (e.g., INFO, WARNING, CRITICAL).
* **Self-Healing API:** Automatically cancels hung or failed imaging tasks to prevent the FOG web server from locking up.

---

## Prerequisites
* A dedicated server running a Debian-based Linux distribution (Ubuntu, Debian).
* `root` (sudo) privileges.
* An internal SMTP relay for email notifications.

---

## Installation Guide

### Step 1: Clone the Repository
Clone or copy this project into your desired directory on the Linux server (e.g., `/opt/script`).

### Step 2: Install Base Dependencies & FOG Server
This suite includes an automated bootstrapper that will install OS dependencies (Python, Git) and launch the official FOG Server installer.

Run the environment installer as root:
```bash
sudo python3 src/setup/install_env.py
```
Note: The script will pause and ask you to answer the standard FOG Project installation prompts. Complete these before moving to Step 3.

### Step 3: Configuration

Before initializing the custom database, you must configure your environment variables and network map.

1. **Secure Credentials (.env file):** Create a new file named strictly .env in the root of your project directory (`/opt/fog-automation/.env`). Add your configurations here (the SMTP feature is optional):
    ```bash
    # Database Configuration
    DB_HOST=127.0.0.1
    DB_USER=fog
    DB_PASSWORD=your_secure_mariadb_password
    DB_NAME=fog_automation

    # FOG Server API
    FOG_API_URL=[http://127.0.0.1/fog]
    FOG_TASK_TYPE=8

    # Email Notification System
    SMTP_HOST=127.0.0.1
    SENDER_EMAIL=fog-server@yourdomain.com
    # Use a comma to separate multiple admin emails
    ADMIN_EMAILS=admin@yourdomain.com,it-support@yourdomain.com
    ```

2. **Define Your Network Layout (room-map.json):** Ensure your JSON room map is placed at `data/mappings/room-map.json`. It must follow this structure so the database can map subnets to FOG Group IDs:

    ``` JSON
    "HH": 
    [
        {
            "room": "Room 101", 
            "ip": "192.168.10.0", 
            "mask": "255.255.255.0", 
            "fog_group_id": 1
        }
    ]
    ```

### Step 4: Initialize the Database

Once MariaDB is running (installed by FOG in Step 2) and your room map is created, build the custom automation tables.

Run the database setup script:

```bash
sudo python3 src/setup/setup_db.py
```

This script will safely build the `rooms`, `host_tracking`, and `host_macs` tables and insert your room data.

---

## Running the Automation (Crontab Setup)

The system is designed to run completely autonomously via Linux cron jobs.

Open the root crontab editor:

```bash
sudo crontab -e
```

Add the following schedules to orchestrate the automation suite (adjust the paths if you installed the project somewhere other than `/opt/script`):

```bash
# 1. Auto-Wake: Runs every 5 minutes (from 07:00 to 19:00 on all weekdays)
*/5 7-19 * * 1-5 /usr/bin/python3 /opt/srcipt/fogserver/src/jobs/auto_wake.py

# 2. Auto-Register: Runs every 5 minutes (from 07:00 to 19:00 on all weekdays)
*/5 7-19 * * 1-5 /usr/bin/python3 /opt/srcipt/fogserver/src/jobs/auto_register.py

# 3. Auto-Scheduler: Runs every hour (from 07:00 to 19:00 on all weekdays)
0 7-19 * * 1-5 /usr/bin/python3 /opt/srcipt/fogserver/src/jobs/auto_scheduler.py

# 4. Storage Health Check: Runs twice a day (at 08:00 and 20:00)
0 8,20 * * * /usr/bin/python3 /opt/srcipt/fogserver/src/jobs/monitoring/check_storage.py

# 5. Task Monitoring: Runs every hour (from 07:00 to 19:00 on all weekdays)
30 7-19 * * 1-5 /usr/bin/python3 /opt/srcipt/fogserver/src/jobs/monitoring/monitor_tasks.py
```

---

## Logging & Observability
If something goes wrong, the suite is highly observable.

* **Log Location:** Check the `logs/` directory inside the project folder.
* **Activity Log (activity.log):** Records all successful WoL broadcasts, room movements, and standard operations.
* **Error Log (error.log):** Records full stack traces of any API failures, DB disconnections, or code crashes.

Note: The system automatically rotates log files daily and retains 60 days of history to prevent disk bloat.