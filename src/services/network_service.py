import socket
from typing import List

import src.notifications.mailer as mailer
from src.data.db_manager import db
from src.models.room import Room

from src.logger.logger import LogManager
logging = LogManager.get_logger("network_service")

class NetworkService:
    """
    Service for managing network-related operations, including fetching room information and sending Wake-on-LAN packets.
    """

    def get_all_rooms(self) -> List[Room]:
        """
        Fetches all rooms from the database.
        Returns:
            List[Room]: A list of Room objects.
        """
        rooms = []
        with db.get_connection() as conn:
            with conn.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM rooms")
                
                for row in cursor.fetchall():
                    rooms.append(Room(
                        name=row['room_name'],
                        ip_address=row['ip_address'],
                        subnet_mask=row['subnet_mask'],
                        fog_group_id=row['fog_group_id']
                    ))
        return rooms

    def send_magic_packet(self, mac_address: str, broadcast_ip: str) -> bool:
        """
        Sends a Wake-on-LAN (WOL) magic packet to a specified MAC address.
        Args:
            mac_address (str): The MAC address of the target device.
            broadcast_ip (str): The broadcast IP address of the network.
        Returns:
            bool: True if the packet was sent successfully, False otherwise.
        """
        clean_mac = mac_address.replace(':', '').replace('-', '')
        if len(clean_mac) != 12 or not broadcast_ip:
            return False
        
        magic_packet = bytes.fromhex('FF' * 6 + clean_mac * 16)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.settimeout(2.0)
                s.sendto(magic_packet, (broadcast_ip, 9))
            return True
        except Exception as e:
            logging.error(f"WOL Socket Error for {mac_address}: {e}")
            return False

    def process_room_wake(self, room_name: str, broadcast_ip: str, macs_to_wake: List[str]):
        """
        Processes the Wake-on-LAN (WOL) operation for a specific room.
        Args:
            room_name (str): The name of the room.
            broadcast_ip (str): The broadcast IP address of the network.
            macs_to_wake (List[str]): A list of MAC addresses to send WOL packets to.
        """
        successful_macs = []
        failed_macs = []
        
        for mac in macs_to_wake:
            if self.send_magic_packet(mac, broadcast_ip):
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
                    f"Sent Wake-on-LAN packets to {success_count} devices in room '{room_name}', but {len(failed_macs)} failed to send.\n\nSkipped MACs: {', '.join(failed_macs)}",
                    priority="normal"
                )
            else:
                logging.info(f"WOL STATE-AWARE: Successfully sent all {success_count} packets in '{room_name}'.")
                mailer._send_email(
                    f"[INFO] WOL Sent: {room_name}",
                    f"Sent Wake-on-LAN packets to all {success_count} devices in room '{room_name}'.",
                    priority="low"
                )