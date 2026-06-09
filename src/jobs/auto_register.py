from src.services.host_service import HostService
from src.services.network_service import NetworkService
import src.notifications.mailer as mailer

from src.logger.logger import LogManager
logging = LogManager.get_logger("auto_register")

def process_new_hosts():
    """
    Processes new hosts by approving pending hosts, updating IP and MAC addresses,
    routing hosts to the appropriate rooms, triggering imaging tasks if necessary,
    and syncing host information to the database. It also cleans up stale hosts that haven't been seen for a specified number of days.
    """
    network_service = NetworkService()
    host_service = HostService()
    
    try:
        rooms = network_service.get_all_rooms()
        all_hosts = host_service.fetch_fog_hosts()
        
        valid_hosts = host_service.handle_duplicate_macs(all_hosts)
        
        for host in valid_hosts:
            if host.is_pending:
                host_service.approve_host(host)
                
            if not host.ip or not host.macs:
                continue

            if host_service.ip_has_changed(host):
                target_group_id = host_service.route_host_to_room(host, rooms)
                needs_imaging = host_service.update_fog_group_associations(host, target_group_id, rooms)
                
                if host.is_pending or needs_imaging:
                    host_service.trigger_imaging_task(host)
                    
                host_service.sync_host_to_db(host, target_group_id)
            
        host_service.cleanup_stale_hosts(days_stale=14)

    except Exception as e:
        logging.error("Fatal error in Auto-Register.", exc_info=True)
        mailer._send_email("[CRITICAL] Auto-Register Failed", f"Error:\n{e}", priority="high")