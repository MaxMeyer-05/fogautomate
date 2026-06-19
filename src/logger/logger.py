import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict

root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

class LogManager:
    """
    Manages loggers for different modules.
    """
    _loggers: Dict[str, logging.Logger] = {}

    @classmethod
    def get_logger(cls, module_name: str) -> logging.Logger:
        """
        Returns a logger for the specified module.
        Args:
            module_name (str): The name of the module for which to get the logger.
        Returns:
            logging.Logger: The logger instance for the specified module.
        """
        if module_name in cls._loggers:
            return cls._loggers[module_name]

        clean_name = module_name.split('.')[-1]
        
        if clean_name == '__main__':
            clean_name = 'dispatcher'

        logger = logging.getLogger(clean_name)
        
        if not logger.handlers:
            logger.setLevel(logging.INFO)
            
            logger.propagate = False           
            
            log_dir = root_path / "logs"                
            log_dir.mkdir(parents=True, exist_ok=True)
            
            formatter = logging.Formatter(
                fmt="%(asctime)s - %(levelname)s - [%(name)s:%(lineno)d] - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )

            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)

            log_file = log_dir / f"{clean_name}.log"
            file_handler = RotatingFileHandler(
                str(log_file), maxBytes=5 * 1024 * 1024, backupCount=14
            )
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)

            logger.addHandler(console_handler)
            logger.addHandler(file_handler)

        cls._loggers[module_name] = logger
        return logger