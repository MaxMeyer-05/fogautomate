from contextlib import contextmanager
import mysql.connector
from config.config import FOG_DB_CONFIG

from src.logger.logger import LogManager
logging = LogManager.get_logger("db_manager")

class DatabaseManager:
    """
    Manages the database connection pool and provides a context manager for database connections.
    Implements the singleton pattern to ensure a single instance.   
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.pool_name = "fog_automation_pool"
        self.pool_size = 5
        self.pool = None
        
        try:
            self.pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name=self.pool_name,
                pool_size=self.pool_size,
                pool_reset_session=True,
                **FOG_DB_CONFIG
            )
            logging.info("DatabaseManager: MariaDB connection pool successfully initialized.")
        except mysql.connector.Error as e:
            logging.error(f"DatabaseManager: Failed to initialize connection pool. Error: {e}", exc_info=True)

    @contextmanager
    def get_connection(self):
        """
        Provides a context manager for acquiring a database connection from the pool.
        """
        if self.pool is None:
            logging.error("DatabaseManager: Attempted to get a connection, but the pool is down.")
            raise ConnectionError("Database pool is not initialized.")
            
        conn = None
        try:
            conn = self.pool.get_connection()
            yield conn
        except mysql.connector.Error as e:
            logging.error(f"DatabaseManager: Query execution failed: {e}")
            raise
        finally:
            if conn and conn.is_connected():
                conn.close()

db = DatabaseManager()