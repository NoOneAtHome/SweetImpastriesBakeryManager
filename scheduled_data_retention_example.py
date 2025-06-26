#!/usr/bin/env python3
"""
Example of how to integrate DataRetentionService with a scheduler.

This example shows how the DataRetentionService can be used with APScheduler
for automatic data purging as mentioned in PRD Section 6.4.
"""

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from data_retention import DataRetentionService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def scheduled_data_purge():
    """
    Scheduled function to purge old sensor readings.
    
    This function will be called automatically by the scheduler.
    """
    logger.info("Starting scheduled data purge...")
    
    try:
        # Initialize the data retention service
        service = DataRetentionService()
        
        # Run the purge operation
        result = service.purge_old_readings()
        
        if result['success']:
            logger.info(f"Purge completed successfully: {result['records_deleted']} records deleted")
            logger.info(f"Retention period: {result['retention_months']} months")
            logger.info(f"Cutoff date: {result['cutoff_date']}")
        else:
            logger.error(f"Purge failed: {result['error_message']}")
            
    except Exception as e:
        logger.error(f"Unexpected error during scheduled purge: {e}")

def main():
    """
    Main function to set up and start the scheduler.
    
    This example sets up a scheduler that runs data purging:
    - Daily at 2:00 AM (when system load is typically low)
    - Can be customized based on operational requirements
    """
    logger.info("Setting up scheduled data retention service...")
    
    # Create scheduler
    scheduler = BlockingScheduler()
    
    # Schedule daily purge at 2:00 AM
    scheduler.add_job(
        func=scheduled_data_purge,
        trigger=CronTrigger(hour=2, minute=0),  # Daily at 2:00 AM
        id='daily_data_purge',
        name='Daily Data Purge',
        replace_existing=True
    )
    
    # Alternative scheduling options (commented out):
    
    # Weekly purge (Sundays at 3:00 AM)
    # scheduler.add_job(
    #     func=scheduled_data_purge,
    #     trigger=CronTrigger(day_of_week=6, hour=3, minute=0),
    #     id='weekly_data_purge',
    #     name='Weekly Data Purge'
    # )
    
    # Monthly purge (1st of each month at 1:00 AM)
    # scheduler.add_job(
    #     func=scheduled_data_purge,
    #     trigger=CronTrigger(day=1, hour=1, minute=0),
    #     id='monthly_data_purge',
    #     name='Monthly Data Purge'
    # )
    
    logger.info("Scheduler configured. Starting...")
    logger.info("Press Ctrl+C to stop the scheduler")
    
    try:
        # Start the scheduler
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    except Exception as e:
        logger.error(f"Scheduler error: {e}")

if __name__ == "__main__":
    main()