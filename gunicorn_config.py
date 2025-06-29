# gunicorn_config.py
import logging
import os
from app import create_app
from polling_service import create_polling_service
from config import ProductionConfig, DevelopmentConfig

# Global variable to hold the polling service instance per worker
# This will be unique for each forked worker process
polling_service_instance = None

def post_fork(server, worker):
    """
    Called just after a worker has been forked.
    Initializes and starts the PollingService for this worker.
    """
    global polling_service_instance
    logging.info(f"Worker {worker.pid} forked. Initializing PollingService.")

    # Determine the configuration based on FLASK_ENV
    flask_env = os.environ.get('FLASK_ENV', 'production')
    if flask_env == 'development':
        config_class = DevelopmentConfig
    else:
        config_class = ProductionConfig

    # Create a minimal app instance to get the config
    # This is a workaround to get the config without fully initializing Flask app context
    temp_app = create_app(config_class=config_class)
    
    polling_service_instance = create_polling_service(config_class=config_class)
    polling_service_instance.start()
    logging.info(f"PollingService started for worker {worker.pid}.")

def on_exit(server):
    """
    Called just before a worker is exited.
    Shuts down the PollingService for this worker.
    """
    global polling_service_instance
    if polling_service_instance:
        logging.info("PollingService shutting down for worker.")
        polling_service_instance.close()
        logging.info("PollingService shut down for worker.")

def worker_abort(worker):
    """
    Called when a worker receives the SIGABRT signal.
    Ensures the polling service is shut down even on abnormal termination.
    """
    global polling_service_instance
    if polling_service_instance:
        logging.warning(f"Worker {worker.pid} aborted. Attempting to shut down PollingService.")
        polling_service_instance.close()
        logging.warning(f"PollingService shut down for aborted worker {worker.pid}.")

# Set the log level for Gunicorn itself to match the application's log level
# This might be overridden by Gunicorn's own logging configuration
loglevel = os.environ.get('LOG_LEVEL', 'INFO').lower()
if loglevel == 'debug':
    logging.getLogger('gunicorn.error').setLevel(logging.DEBUG)
    logging.getLogger('gunicorn.access').setLevel(logging.DEBUG)
elif loglevel == 'info':
    logging.getLogger('gunicorn.error').setLevel(logging.INFO)
    logging.getLogger('gunicorn.access').setLevel(logging.INFO)
elif loglevel == 'warning':
    logging.getLogger('gunicorn.error').setLevel(logging.WARNING)
    logging.getLogger('gunicorn.access').setLevel(logging.WARNING)
elif loglevel == 'error':
    logging.getLogger('gunicorn.error').setLevel(logging.ERROR)
elif loglevel == 'critical':
    logging.getLogger('gunicorn.error').setLevel(logging.CRITICAL)

# You can also set other Gunicorn options here, e.g., number of workers
# workers = 2 # Example: set number of workers