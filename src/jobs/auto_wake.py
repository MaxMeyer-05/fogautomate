import sys
import socket
import ipaddress
from pathlib import Path
from typing import List, Dict, Any

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

def get_active_host_ids() -> List[int]:
    """
    Fetches FOG tasks and extracts host IDs securely.
     Returns:
        List[int]: A list of active host IDs associated with current FOG tasks.
    """
    success, response = fog_api_request("GET", "task/active")
    if not success or not response:
        return []
        
    active_tasks = response.get('tasks', [])
    if isinstance(active_tasks, dict):
        active_tasks = list(active_tasks.values())
        
    return [int(str(t.get('hostID', '0'))) for t in active_tasks if t.get('hostID')]

def get_rooms_to_wake(cursor, host_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Fetch rooms that need to be woken based on active host IDs.
    Args:
        cursor: The database cursor.
        host_ids (List[int]): A list of active host IDs.
    Returns:
        List[Dict[str, Any]]: A list of room dictionaries.
    """
    format_strings = ','.join(['%s'] * len(host_ids))
    query = f"""
        SELECT DISTINCT r.room_name, r.ip_address, r.subnet_mask, r.fog_group_id
        FROM host_tracking ht
        JOIN rooms r ON ht.assigned_group_id = r.fog_group_id
        WHERE ht.host_id IN ({format_strings})
    """
    cursor.execute(query, tuple(host_ids))
    return cursor.fetchall()

def get_macs_for_room(cursor, group_id: int) -> List[str]:
    """
    Fetch MAC addresses for a given room based on its FOG group ID.
    Args:
        cursor: The database cursor.
        group_id (int): The FOG group ID of the room.
    Returns:
        List[str]: A list of MAC addresses associated with the room.
    """
    cursor.execute("""
        SELECT m.mac_address 
        FROM host_macs m
        JOIN host_tracking h ON m.host_id = h.host_id
        WHERE h.assigned_group_id = %s
    """, (group_id,))
    return [row['mac_address'] for row in cursor.fetchall()]

def process_room_wake(room_name: str, broadcast_ip: str, macs_to_wake: List[str]):
    """
    Iterates through MACs and reports granular success states.
    Args:
        room_name (str): The name of the room.
        broadcast_ip (str): The broadcast IP address for the room.
        macs_to_wake (List[str]): A list of MAC addresses to wake.
    """
    successful_macs = []
    failed_macs = []
    
    for mac in macs_to_wake:
        if send_magic_packet(mac, broadcast_ip):
            successful_macs.append(mac)
        else:
            failed_macs.append(mac)
    
    success_count = len(successful_macs)
    total_macs = len(macs_to_wake)

    if total_macs > 0:
        if success_count == 0:
            logging.error(f"WOL FAILED: Server socket failed on all {total_macs} MACs in '{room_name}'.")
            mailer._send_email(
                f"[CRITICAL] WOL Failed: {room_name}",
                f"Attempted to send WOL packets for room '{room_name}', but the server network socket failed on all {total_macs} MAC addresses.\n\nFailed MACs: {', '.join(failed_macs)}",
                priority="high"
            )
        elif success_count < total_macs:
            logging.warning(f"WOL PARTIAL: {success_count}/{total_macs} sent in '{room_name}'. Failed MACs: {failed_macs}")
            mailer._send_email(
                f"[WARNING] WOL Partial Success: {room_name}",
                f"Sent Wake-on-LAN packets to {success_count} devices in room '{room_name}', but {len(failed_macs)} failed to send.\n\nSkipped MACs: {', '.join(failed_macs)}\n\nPlease check the error.log for specific socket errors.",
                priority="normal"
            )
        else:
            logging.info(f"WOL STATE-AWARE: Successfully sent all {success_count} packets in '{room_name}'.")
            mailer._send_email(
                f"[INFO] WOL Sent: {room_name}",
                f"Sent Wake-on-LAN packets to all {success_count} devices in room '{room_name}' for active deployment.",
                priority="low"
            )

def run_wake_cycle():
    """
    Main execution function for the Auto-Wake job.
    """
    try:
        active_host_ids = get_active_host_ids()
        if not active_host_ids:
            return
            
        with db_session() as conn:
            cursor = conn.cursor(dictionary=True)
            rooms_to_wake = get_rooms_to_wake(cursor, active_host_ids)
            
            for room in rooms_to_wake:
                room_name = room['room_name']
                broadcast_ip = get_directed_broadcast(room['ip_address'], room['subnet_mask'])
                macs_to_wake = get_macs_for_room(cursor, room['fog_group_id'])
                
                process_room_wake(room_name, broadcast_ip, macs_to_wake)
                
    except Exception as e:
        logging.error("Fatal Auto-Wake execution error.", exc_info=True)
        mailer._send_email(
            "[CRITICAL] Auto-Wake Execution Failure",
            f"The Wake-on-LAN script crashed unexpectedly.\n\nError: {e}",
            priority="high"
        )

if __name__ == "__main__":
    run_wake_cycle()