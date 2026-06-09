from typing import List, Dict, Set

from src.api.api_manager import api
from src.data.db_manager import db
from src.models.host import Host
from src.models.room import Room
from config.config import FOG_TASK_TYPE

from src.logger.logger import LogManager
logging = LogManager.get_logger("host_service")

UNKNOWN_GROUP_ID = 8

class HostService:
    """
    Service class for managing FOG hosts.
    """
    
    def fetch_fog_hosts(self) -> List[Host]:
        """
        Fetches the list of FOG hosts from the API.
        Returns:
            List[Host]: A list of Host objects.
        """
        success, data = api.execute_fog_request("GET", "host?limit=2000")
        if not success or not data:
            logging.error("Failed to fetch hosts from FOG API.")
            return []
        
        raw_data = data.get('hosts', [])
        host_list = list(raw_data.values()) if isinstance(raw_data, dict) else raw_data
        
        hosts = []
        for item in host_list:
            try:
                host_id = int(str(item.get('id', '0')))
                if host_id == 0:
                    continue
                
                self._heal_primary_mac(host_id, item)
                    
                is_pending = str(item.get('pending', '0')) == '1' or str(item.get('hostPending', '0')) == '1'
                
                host = Host(
                    id=host_id,
                    name=str(item.get('name', '')),
                    ip=str(item.get('ip', '')),
                    macs=self._extract_macs(item),
                    is_pending=is_pending
                )
                hosts.append(host)
            except Exception as e:
                logging.error(f"Error parsing host data for ID {item.get('id')}: {e}")
                
        return hosts

    def _heal_primary_mac(self, host_id: int, raw_item: dict):
        """
        Detects if the Primary MAC is a loopback and promotes a valid Additional MAC.
        Args:
            host_id (int): The ID of the host being processed.
            raw_item (dict): The raw host data from the API.
        """
        primac = str(raw_item.get('primac', '')).lower()
        invalid_macs = {'', '00:00:00:00:00:00', '00-00-00-00-00-00'}
        
        if primac not in invalid_macs:
            return
            
        valid_candidates = []
        for key in ['macs', 'additionalMACs']:
            val = raw_item.get(key)
            if isinstance(val, list):
                for m in val:
                    mac_str = ""
                    if isinstance(m, str): 
                        mac_str = m.lower()
                    elif isinstance(m, dict) and m.get('mac'): 
                        mac_str = str(m.get('mac', '')).lower()
                        
                    if mac_str and mac_str not in invalid_macs:
                        valid_candidates.append(mac_str)
        
        if valid_candidates:
            new_primac = valid_candidates[0]
            logging.info(f"SELF-HEALING: Host ID {host_id} has a loopback Primary MAC. Promoting {new_primac} to primary.")
            api.execute_fog_request("PUT", f"host/{host_id}", {"primac": new_primac})

    def _extract_macs(self, item: dict) -> List[str]:
        """
        Extracts all valid MAC addresses from the given host item.
        Args:
            item (dict): The raw host data from the API.
        Returns:
            List[str]: A list of valid MAC addresses.
        """
        macs = set()
        primac = item.get('primac', '').lower()
        if primac:
            macs.add(primac)
            
        for key in ['macs', 'additionalMACs']:
            val = item.get(key)
            if isinstance(val, list):
                for m in val:
                    if isinstance(m, str):
                        macs.add(m.lower())
                    elif isinstance(m, dict) and m.get('mac'):
                        macs.add(str(m.get('mac', '')).lower())
                        
        invalid_macs = {'', '00:00:00:00:00:00', '00-00-00-00-00-00'}
        return [m for m in macs if m not in invalid_macs]

    def handle_duplicate_macs(self, all_hosts: List[Host]) -> List[Host]:
        """
        Handles duplicate MAC addresses among the given hosts.
        Args:
            all_hosts (List[Host]): A list of Host objects.
        Returns:
            List[Host]: A list of Host objects with duplicates removed.
        """
        mac_to_host: Dict[str, int] = {}
        hosts_to_delete: Set[int] = set()
        
        for host in all_hosts:
            if not host.macs:
                continue
            for mac in host.macs:
                if mac in mac_to_host:
                    existing_id = mac_to_host[mac]
                    if existing_id != host.id:
                        older_id = min(existing_id, host.id)
                        newer_id = max(existing_id, host.id)
                        
                        hosts_to_delete.add(newer_id)
                        mac_to_host[mac] = older_id
                else:
                    mac_to_host[mac] = host.id
        
        valid_hosts = []
        for host in all_hosts:
            if host.id in hosts_to_delete:
                logging.warning(f"GHOST DETECTED: Erasing new duplicate registration '{host.name}' (ID: {host.id}).")
                api.execute_fog_request("DELETE", f"host/{host.id}")
                
                with db.get_connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute("DELETE FROM host_tracking WHERE host_id = %s", (host.id,))
                    conn.commit()
            else:
                valid_hosts.append(host)
                
        return valid_hosts

    def approve_host(self, host: Host) -> bool:
        """
        Approves the given host by updating its pending status in the FOG API.
        Args:
            host (Host): The host to approve.
        Returns:
            bool: True if the approval was successful, False otherwise.
        """
        success, _ = api.execute_fog_request("PUT", f"host/{host.id}", {"hostPending": "0", "pending": "0"})
        if success:
            logging.info(f"APPROVED: {host.name}.")
        return success

    def ip_has_changed(self, host: Host) -> bool:
        with db.get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT last_ip FROM host_tracking WHERE host_id = %s", (host.id,))
                row = cursor.fetchone()
                
                if not row:
                    return True
                    
                return row['last_ip'] != host.ip

    def route_host_to_room(self, host: Host, rooms: List[Room]) -> int:
        """
        Routes the given host to the appropriate room based on its IP address.
        Args:
            host (Host): The host to route.
            rooms (List[Room]): A list of Room objects.
        Returns:
            int: The FOG group ID of the room the host belongs to, or UNKNOWN_GROUP_ID if not found.
        """
        for room in rooms:
            if room.contains_ip(host.ip):
                return room.fog_group_id
        return UNKNOWN_GROUP_ID

    def update_fog_group_associations(self, host: Host, target_group_id: int, rooms: List[Room]) -> bool:
        """
        Updates the FOG group associations for the given host.
        Args:
            host (Host): The host to update.
            target_group_id (int): The target FOG group ID.
            rooms (List[Room]): A list of Room objects.
        Returns:
            bool: True if the update was successful, False otherwise.
        """
        success, host_detail = api.execute_fog_request("GET", f"host/{host.id}")
        if not success or not host_detail:
            return False
            
        valid_room_ids = [r.fog_group_id for r in rooms]
        if UNKNOWN_GROUP_ID not in valid_room_ids:
            valid_room_ids.append(UNKNOWN_GROUP_ID)
            
        associations = host_detail.get('groupAssociations', [])
        current_room_groups = [
            int(str(g.get('groupID') or g.get('id', '0')))
            for g in associations 
            if int(str(g.get('groupID') or g.get('id', '0'))) in valid_room_ids
        ]
        
        needs_imaging = False
        
        if current_room_groups and target_group_id not in current_room_groups:
            logging.info(f"MOVE DETECTED: '{host.name}' changed rooms.")
            for assoc in associations:
                assoc_group_id = int(str(assoc.get('groupID') or assoc.get('id', '0')))
                if assoc_group_id in current_room_groups:
                    api.execute_fog_request("DELETE", f"groupassociation/{assoc.get('id')}")
            needs_imaging = True

        if target_group_id not in current_room_groups:
            assign_success, _ = api.execute_fog_request("POST", "groupassociation", {"hostID": host.id, "groupID": target_group_id})
            if assign_success:
                logging.info(f"ASSIGNED: '{host.name}' added to target group ID {target_group_id}.")
                
        return needs_imaging

    def trigger_imaging_task(self, host: Host) -> bool:
        """
        Triggers an imaging task for the given host.
        Args:
            host (Host): The host to trigger the imaging task for.
        Returns:
            bool: True if the imaging task was successfully triggered, False otherwise.
        """
        success, _ = api.execute_fog_request("POST", f"host/{host.id}/task", {"taskTypeID": FOG_TASK_TYPE})
        if success:
            logging.info(f"IMAGING TRIGGERED for {host.name}.")
        return success

    def sync_host_to_db(self, host: Host, target_group_id: int):
        """
        Synchronizes the given host's information to the database.
        Args:
            host (Host): The host to synchronize.
            target_group_id (int): The target FOG group ID.
        """
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO host_tracking (host_id, host_name, last_ip, assigned_group_id) 
                    VALUES (%s, %s, %s, %s) 
                    ON DUPLICATE KEY UPDATE host_name=VALUES(host_name), last_ip=VALUES(last_ip), assigned_group_id=VALUES(assigned_group_id)
                """, (host.id, host.name, host.ip, target_group_id))
                
                cursor.execute("DELETE FROM host_macs WHERE host_id = %s", (host.id,))
                for mac in host.macs:
                    cursor.execute("INSERT INTO host_macs (mac_address, host_id) VALUES (%s, %s)", (mac, host.id))
                    
            conn.commit()

    def get_host_info_by_ids(self, host_ids: List[int]) -> Dict[int, Dict]:
        """
        Retrieves host information for the given list of host IDs.
        Args:
            host_ids (List[int]): A list of host IDs to retrieve information for.
        Returns:
            Dict[int, Dict]: A dictionary mapping host IDs to their information.
        """
        if not host_ids:
            return {}
            
        host_info = {}
        with db.get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                format_strings = ','.join(['%s'] * len(host_ids))
                
                query = f"""
                    SELECT h.host_id, h.host_name, r.room_name, m.mac_address
                    FROM host_tracking h
                    JOIN rooms r ON h.assigned_group_id = r.fog_group_id
                    JOIN host_macs m ON h.host_id = m.host_id
                    WHERE h.host_id IN ({format_strings})
                """
                cursor.execute(query, tuple(host_ids))
                
                for row in cursor.fetchall():
                    hid = row['host_id']
                    if hid not in host_info:
                        host_info[hid] = {
                            'name': row['host_name'],
                            'room': row['room_name'],
                            'macs': []
                        }
                    host_info[hid]['macs'].append(row['mac_address'])
                
        return host_info