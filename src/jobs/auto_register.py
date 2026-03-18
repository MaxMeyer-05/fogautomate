import sys
import ipaddress
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Set, Any

root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import logging
from src.utils import db_session, fog_api_request
import src.notifications.mailer as mailer

def get_rooms_from_db() -> List[Dict[str, Any]]:
    """
    Fetch rooms from the database.
    Returns:
        List[Dict[str, Any]]: A list of room dictionaries.
    """
    try:
        with db_session() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT room_name, ip_address, subnet_mask, fog_group_id FROM rooms")
            return cursor.fetchall()
    except Exception:
        logging.error("Failed to fetch rooms from DB.", exc_info=True)
        return []

def get_tracked_macs(db_cursor) -> Dict[str, str]:
    """
    Fetch tracked MAC addresses from the database.
    Args:
        db_cursor: The database cursor.
    Returns:
        Dict[str, str]: A dictionary mapping MAC addresses to their last known IP addresses.
    """
    db_cursor.execute("SELECT m.mac_address, t.last_ip FROM host_macs m JOIN host_tracking t ON m.host_id = t.host_id")
    return {row['mac_address']: row['last_ip'] for row in db_cursor.fetchall()}

def update_local_tracking(db_cursor, host_id: int, host_name: str, host_ip: str, host_macs: List[str], target_group_id: int):
    """
    Update local tracking information for a host in the database.
    Args:
        db_cursor: The database cursor.
        host_id (int): The ID of the host.
        host_name (str): The name of the host.
        host_ip (str): The IP address of the host.
        host_macs (List[str]): A list of MAC addresses associated with the host.
        target_group_id (int): The target group ID for the host.
    """
    db_cursor.execute("""
        INSERT INTO host_tracking (host_id, host_name, last_ip, assigned_group_id) 
        VALUES (%s, %s, %s, %s) 
        ON DUPLICATE KEY UPDATE host_name=VALUES(host_name), last_ip=VALUES(last_ip), assigned_group_id=VALUES(assigned_group_id)
    """, (host_id, host_name, host_ip, target_group_id))
    
    db_cursor.execute("DELETE FROM host_macs WHERE host_id = %s", (host_id,))
    
    for mac in host_macs:
        db_cursor.execute("""
            INSERT INTO host_macs (mac_address, host_id) 
            VALUES (%s, %s) 
        """, (mac, host_id))

def get_all_macs(host: Dict[str, Any]) -> List[str]:
    """
    Get all MAC addresses associated with a host.
    Args:
        host (Dict[str, Any]): The host dictionary.
    Returns:
        List[str]: A list of MAC addresses.
    """
    macs = set()
    
    primac = host.get('primac', '').lower()
    if primac:
        macs.add(primac)
        
    for key in ['macs', 'additionalMACs']:
        val = host.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    macs.add(item.lower())
                elif isinstance(item, dict) and item.get('mac'):
                    macs.add(item.get('mac', '').lower())
                    
    invalid_macs = {'', '00:00:00:00:00:00', '00-00-00-00-00-00'}
    return [m for m in macs if m not in invalid_macs]

def find_room_for_ip(ip_address: str, rooms: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Find the room corresponding to a given IP address.
    Args:
        ip_address (str): The IP address to search for.
        rooms (List[Dict[str, Any]]): A list of room dictionaries.
    Returns:
        Optional[Dict[str, Any]]: The room dictionary if found, None otherwise.
    """
    if not ip_address: 
        return None
    try:
        pc_ip = ipaddress.IPv4Address(ip_address)
    except ValueError:
        return None

    for room in rooms:
        if not room.get('ip_address') or not room.get('subnet_mask'):
            continue
        try:
            network_str = f"{room['ip_address']}/{room['subnet_mask']}"
            if pc_ip in ipaddress.IPv4Network(network_str, strict=False):
                return room
        except ValueError:
            continue
    return None

def handle_duplicate_macs(all_hosts: List[Dict[str, Any]], db_cursor) -> List[Dict[str, Any]]:
    """
    Handle duplicate MAC addresses among hosts.
    Args:
        all_hosts (List[Dict[str, Any]]): A list of host dictionaries.
        db_cursor: The database cursor.
    Returns:
        List[Dict[str, Any]]: A list of valid host dictionaries.
    """
    mac_to_host: Dict[str, int] = {}
    hosts_to_delete: Set[int] = set()
    
    for host in all_hosts:
        host_id = int(host.get('id', 0))
        all_macs = get_all_macs(host)
        
        if not all_macs or not host_id:
            continue
            
        for mac in all_macs:
            if mac in mac_to_host:
                existing_id = mac_to_host[mac]
                if existing_id != host_id:
                    older_id = min(existing_id, host_id)
                    newer_id = max(existing_id, host_id)
                    hosts_to_delete.add(older_id)
                    mac_to_host[mac] = newer_id
            else:
                mac_to_host[mac] = host_id
            
    valid_hosts: List[Dict[str, Any]] = []
    for host in all_hosts:
        host_id = int(host.get('id', 0))
        host_name = host.get('name', '')
        
        if host_id in hosts_to_delete:
            logging.info(f"DUPLICATE DETECTED: Erasing older ghost host '{host_name}' (ID: {host_id}).")
            fog_api_request("DELETE", f"host/{host_id}")
            db_cursor.execute("DELETE FROM host_tracking WHERE host_id = %s", (host_id,))
        else:
            valid_hosts.append(host)
            
    return valid_hosts

def trigger_host_imaging(host_id: int, host_name: str) -> bool:
    """
    Trigger imaging for a host.
    Args:
        host_id (int): The ID of the host.
        host_name (str): The name of the host.
    Returns:
        bool: True if the imaging was successfully triggered, False otherwise.
    """
    success, _ = fog_api_request("POST", f"host/{host_id}/task", {"taskTypeID": 1})
    if success:
        logging.info(f"IMAGING TRIGGERED for {host_name}.")
    return success

def update_host_groups(host_id: int, host_name: str, target_group_id: int, valid_room_ids: List[int]) -> bool:
    """
    Update the group associations for a host.
    Args:
        host_id (int): The ID of the host.
        host_name (str): The name of the host.
        target_group_id (int): The target group ID for the host.
        valid_room_ids (List[int]): A list of valid room IDs.
    Returns:
        bool: True if the host needs imaging, False otherwise.
    """
    success, host_detail = fog_api_request("GET", f"host/{host_id}")
    if not success or not host_detail:
        return False
        
    associations = host_detail.get('groupAssociations', [])
    current_room_groups = [
        int(g.get('groupID') or g.get('id', 0)) 
        for g in associations 
        if int(g.get('groupID') or g.get('id', 0)) in valid_room_ids
    ]
    
    needs_imaging = False
    
    if current_room_groups and target_group_id not in current_room_groups:
        logging.info(f"MOVE DETECTED: {host_name} changed rooms.")
        for assoc in associations:
            assoc_group_id = int(assoc.get('groupID') or assoc.get('id', 0))
            if assoc_group_id in current_room_groups:
                fog_api_request("DELETE", f"groupassociation/{assoc.get('id')}")
        needs_imaging = True

    if target_group_id not in current_room_groups:
        assign_success, _ = fog_api_request("POST", "groupassociation", {"hostID": host_id, "groupID": target_group_id})
        if assign_success:
            logging.info(f"ASSIGNED: {host_name} added to target group ID {target_group_id}.")
            
    return needs_imaging

def process_new_hosts():
    """
    Process new hosts by updating their group associations and triggering imaging if necessary.
    """
    rooms = get_rooms_from_db()
    if not rooms:
        return
    
    valid_room_ids = [int(r['fog_group_id']) for r in rooms]
    
    try:
        with db_session() as db_conn:
            db_cursor = db_conn.cursor(dictionary=True)
            tracked_macs = get_tracked_macs(db_cursor)
            
            success, hosts_data = fog_api_request("GET", "host?limit=2000")
            if not success or not hosts_data:
                return
                
            raw_data = hosts_data.get('hosts', [])
            all_hosts = list(raw_data.values()) if isinstance(raw_data, dict) else raw_data
            
            valid_hosts = handle_duplicate_macs(all_hosts, db_cursor)
            db_conn.commit()
            
            for host in valid_hosts:
                host_id = int(host.get('id', 0))
                host_name = host.get('name', '')
                host_ip = host.get('ip', '')
                all_macs = get_all_macs(host)
                
                is_pending = str(host.get('pending', '0')) == '1' or str(host.get('hostPending', '0')) == '1'
                is_new_registration = False
                
                if is_pending:
                    app_success, _ = fog_api_request("PUT", f"host/{host_id}", {"hostPending": "0", "pending": "0"})
                    if app_success:
                        logging.info(f"APPROVED: {host_name}.")
                        is_new_registration = True
                    
                if not host_ip or not all_macs:
                    continue

                last_known_ip = None
                for mac in all_macs:
                    if mac in tracked_macs:
                        last_known_ip = tracked_macs[mac]
                        break

                if last_known_ip == host_ip and not is_new_registration:
                    continue 

                room = find_room_for_ip(host_ip, rooms)
                if not room: 
                    continue 

                target_group_id = int(room['fog_group_id'])
                
                needs_imaging = update_host_groups(host_id, host_name, target_group_id, valid_room_ids)
                if is_new_registration:
                    needs_imaging = True

                if needs_imaging:
                    trigger_host_imaging(host_id, host_name)

                update_local_tracking(db_cursor, host_id, host_name, host_ip, all_macs, target_group_id)
                db_conn.commit() 

    except Exception as e:
        logging.error(f"Fatal error in process_new_hosts workflow: {e}", exc_info=True)
        mailer._send_email(
            "[CRITICAL] Auto-Register Execution Failure",
            f"The host registration script crashed unexpectedly. Check the logs for details.",
            priority="high"
        )

def cleanup_stale_hosts():
    """
    Clean up stale hosts by removing them from group associations if they haven't pinged recently.
    """
    try:
        success, hosts_data = fog_api_request("GET", "host?limit=2000")
        if not success or not hosts_data:
            return
            
        raw_data = hosts_data.get('hosts', [])
        all_hosts = list(raw_data.values()) if isinstance(raw_data, dict) else raw_data
        
        cutoff_date = datetime.now() - timedelta(days=14)
        
        for host in all_hosts:
            last_time = host.get('pingtime', '0000-00-00 00:00:00')
            if last_time == '0000-00-00 00:00:00':
                continue
                
            try:
                ping_dt = datetime.strptime(last_time, '%Y-%m-%d %H:%M:%S')
                if ping_dt < cutoff_date:
                    host_id = host['id']
                    
                    detail_success, host_detail = fog_api_request("GET", f"host/{host_id}")
                    if not detail_success or not host_detail:
                        continue
                        
                    removed_count = 0
                    for assoc in host_detail.get('groupAssociations', []):
                        del_success, _ = fog_api_request("DELETE", f"groupassociation/{assoc.get('id')}")
                        if del_success:
                            removed_count += 1
                    
                    if removed_count > 0:
                        logging.info(f"STALE CLEANUP: '{host['name']}' removed from {removed_count} group(s).")
            except ValueError:
                pass 
                
    except Exception as e:
        logging.error(f"Fatal error in cleanup_stale_hosts workflow: {e}", exc_info=True)
        mailer._send_email(
            "[CRITICAL] Stale Hosts Cleanup Failure",
            f"The host cleanup script crashed unexpectedly. Check the logs for details.",
            priority="high"
        )

if __name__ == "__main__":
    process_new_hosts()
    cleanup_stale_hosts()