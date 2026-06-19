from dataclasses import dataclass
import ipaddress

@dataclass
class Room:
    """
    Represents a room with network configuration for fog computing.
    Args:
        name (str): The name of the room.
        ip_address (str): The IP address of the room.
        subnet_mask (str): The subnet mask for the room's network.
        fog_group_id (int): The identifier for the fog group associated with the room.
    """
    name: str
    ip_address: str
    subnet_mask: str
    fog_group_id: int

    def contains_ip(self, ip_str: str) -> bool:
        """
        Checks if the given IP address is within the room's network.
        Args:
            ip_str (str): The IP address to check.
        Returns:
            bool: True if the IP address is within the room's network, False otherwise.
        """
        if not ip_str or self.ip_address == "0.0.0.0":
            return False
        try:
            network = ipaddress.IPv4Network(f"{self.ip_address}/{self.subnet_mask}", strict=False)
            return ipaddress.IPv4Address(ip_str) in network
        except ValueError:
            return False

    @property
    def broadcast_address(self) -> str:
        """
        Returns the broadcast address for the room's network.
        Returns:
            str: The broadcast address of the room's network, or an empty string if invalid.
        """
        if self.ip_address == "0.0.0.0":
            return ""
        try:
            network = ipaddress.IPv4Network(f"{self.ip_address}/{self.subnet_mask}", strict=False)
            return str(network.broadcast_address)
        except ValueError:
            return ""