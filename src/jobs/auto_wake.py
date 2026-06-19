import src.notifications.mailer as mailer
from src.services.task_service import TaskService
from src.services.host_service import HostService
from src.services.network_service import NetworkService

from src.logger.logger import LogManager
logging = LogManager.get_logger("auto_wake")

def run_wake_cycle():
    """
    Executes a wake cycle for all active tasks.
    """
    task_service = TaskService()
    host_service = HostService()
    network_service = NetworkService()
    
    try:
        active_tasks = task_service.fetch_active_tasks()
        if not active_tasks:
            return
            
        host_ids = [t.host_id for t in active_tasks]
        host_info = host_service.get_host_info_by_ids(host_ids)
        rooms = network_service.get_all_rooms()
        room_dict = {r.name: r for r in rooms}
        
        room_wake_targets = {}
        for hid, info in host_info.items():
            r_name = info['room']
            if r_name not in room_wake_targets:
                room_wake_targets[r_name] = set()
            for mac in info['macs']:
                room_wake_targets[r_name].add(mac)
                
        for r_name, macs in room_wake_targets.items():
            room_obj = room_dict.get(r_name)
            if not room_obj or not room_obj.broadcast_address:
                continue
                
            network_service.process_room_wake(r_name, room_obj.broadcast_address, list(macs))
            
    except Exception as e:
        logging.error("Fatal Auto-Wake execution error.", exc_info=True)
        mailer._send_email("[CRITICAL] Auto-Wake Execution Failure", f"Error:\n\n{e}", priority="high")

if __name__ == "__main__":
    run_wake_cycle()