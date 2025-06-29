# gunicorn_config.py
import logging
import os
from app import create_app
from config import ProductionConfig, DevelopmentConfig

def post_fork(server, worker):
    """
    Called just after a worker has been forked.
    The polling service is now automatically initialized within the Flask app factory.
    """
    logging.info(f"Worker {worker.pid} forked. Polling service will be initialized automatically by Flask app.")

def on_exit(server):
    """
    Called just before a worker is exited.
    The polling service cleanup is now handled by Flask app teardown handlers.
    """
    logging.info("Worker exiting. Polling service cleanup handled by Flask app teardown.")

def worker_abort(worker):
    """
    Called when a worker receives the SIGABRT signal.
    The polling service cleanup is now handled by Flask app teardown handlers.
    """
    logging.warning(f"Worker {worker.pid} aborted. Polling service cleanup handled by Flask app teardown.")

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