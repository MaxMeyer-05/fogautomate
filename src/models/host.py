from dataclasses import dataclass
from typing import List

@dataclass
class Host:
    """
    Represents a host in the network.
    Args:
        id (int): The unique identifier of the host.
        name (str): The name of the host.
        ip (str): The IP address of the host.
        macs (List[str]): A list of MAC addresses associated with the host.
        is_pending (bool): Indicates whether the host is pending approval or not.
    """
    id: int
    name: str
    ip: str
    macs: List[str]
    is_pending: bool