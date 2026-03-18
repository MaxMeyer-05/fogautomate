import sys
import socket
import ipaddress
from pathlib import Path

root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import logging
from src.utils import db_session, fog_api_request
import src.notifications.mailer as mailer

def get_directed_broadcast(ip_str: str, mask_str: str) -> str:
    """
    Calculate the directed broadcast address for a given IP and subnet mask.
    Args:
        ip_str (str): The IP address in string format (e.g., "192.168.1.1").
        mask_str (str): The subnet mask in string format (e.g., "255.255.255.0").
    Returns:
        str: The directed broadcast address in string format.
    """
    network = ipaddress.IPv4Network(f"{ip_str}/{mask_str}", strict=False)
    return str(network.broadcast_address)

def send_magic_packet(mac_address: str, broadcast_ip: str) -> bool:
    """
    Send a Wake-on-LAN magic packet to the specified MAC address via the broadcast IP.
    Args:
        mac_address (str): The target device's MAC address (e.g., "AA:BB:CC:11:22:33").
        broadcast_ip (str): The broadcast IP address to send the packet to (e.g., "192.168.1.255").
    Returns:
        bool: True if the packet was successfully sent, False otherwise.
    """
    clean_mac = mac_address.replace(':', '').replace('-', '')
    if len(clean_mac) != 12:
        return False
    
    magic_packet = bytes.fromhex('FF' * 6 + clean_mac * 16)
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(2.0)
            s.sendto(magic_packet, (broadcast_ip, 9))
        return True
    except Exception as e:
        logging.error(f"WOL Error for MAC {mac_address}: {e}")
        return False

def run_wake_cycle():
    """
    Execute the wake-on-LAN cycle for active tasks.
    """
    try:
        success, response = fog_api_request("GET", "task/active")
        if not success or not response:
            return
            
        active_tasks = response.get('tasks', [])
        if isinstance(active_tasks, dict):
            active_tasks = list(active_tasks.values())
            
        active_host_ids = [int(t.get('hostID')) for t in active_tasks if t.get('hostID')]
        
        if not active_host_ids:
            return
            
        with db_session() as conn:
            cursor = conn.cursor(dictionary=True)
            format_strings = ','.join(['%s'] * len(active_host_ids))
            
            query = f"""
                SELECT DISTINCT r.room_name, r.ip_address, r.subnet_mask, r.fog_group_id
                FROM host_tracking ht
                JOIN rooms r ON ht.assigned_group_id = r.fog_group_id
                WHERE ht.host_id IN ({format_strings})
            """
            cursor.execute(query, tuple(active_host_ids))
            rooms_to_wake = cursor.fetchall()
            
            for room in rooms_to_wake:
                room_name = room['room_name']
                broadcast_ip = get_directed_broadcast(room['ip_address'], room['subnet_mask'])
                
                cursor.execute("""
                    SELECT m.mac_address 
                    FROM host_macs m
                    JOIN host_tracking h ON m.host_id = h.host_id
                    WHERE h.assigned_group_id = %s
                """, (room['fog_group_id'],))

                macs_to_wake = [row['mac_address'] for row in cursor.fetchall()]
                success_count = sum(1 for mac in macs_to_wake if send_magic_packet(mac, broadcast_ip))
                
                if success_count == len(macs_to_wake) and success_count > 0:
                    logging.info(f"WOL STATE-AWARE: Woke up {success_count} PCs in '{room_name}' (Active deployment waiting).")
                    mailer._send_email(
                        f"[INFO] WOL Sent: {room_name}",
                        f"Sent Wake-on-LAN packets to {success_count} devices in room '{room_name}' for active deployment.",
                        priority="low"
                    )
                elif success_count == 0:
                    mailer._send_email(
                        f"[CRITICAL] WOL Failed: {room_name}",
                        f"Attempted to send WOL packets for room '{room_name}' but the server network socket failed on all {len(macs_to_wake)} MAC addresses.",
                        priority="high"
                    )
                elif success_count < len(macs_to_wake):
                    mailer._send_email(
                        f"[WARNING] WOL Partial Success: {room_name}",
                        f"Sent Wake-on-LAN packets to {success_count} out of {len(macs_to_wake)} devices in room '{room_name}' for active deployment. Check server logs for details."
                    )
                
    except Exception as e:
        logging.error(f"Fatal Auto-Wake execution error: {e}", exc_info=True)
        mailer._send_email(
            "[CRITICAL] Auto-Wake Execution Failure",
            f"The Wake-on-LAN script crashed unexpectedly. Check the logs for details.",
            priority="high"
        )

if __name__ == "__main__":
    run_wake_cycle()