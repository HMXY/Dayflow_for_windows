"""Daily summary manager - schedules and manages automatic daily summary generation."""

import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from dayflow.utils.config import Config
from dayflow.services.daily_summary_service import DailySummaryService

logger = logging.getLogger(__name__)


class DailySummaryManager:
    """Manager for automatic daily summary generation."""

    def __init__(self, config: Config):
        """
        Initialize daily summary manager.

        Args:
            config: Application configuration
        """
        self.config = config
        self.scheduler = BackgroundScheduler()

        # Get model name and provider from config
        model_name = getattr(self.config.analysis, "daily_summary_model_name", "gemini-2.0-flash-lite")
        provider = getattr(self.config.analysis, "provider", "gemini")
        api_base_url = getattr(self.config.analysis, "api_base_url", "")
        self.summary_service = DailySummaryService(
            model_name=model_name,
            provider=provider,
            api_base_url=api_base_url,
        )
        self.is_running = False

    def start(self) -> None:
        """Start automatic daily summary scheduling."""
        if self.is_running:
            logger.warning("Daily summary manager already running")
            return

        # Get settings from config
        enabled = getattr(self.config.analysis, "auto_daily_summary", True)
        if not enabled:
            logger.info("Auto daily summary is disabled in settings")
            return

        summary_time = getattr(self.config.analysis, "daily_summary_time", "22:00")

        try:
            # Parse time
            hour, minute = map(int, summary_time.split(":"))

            # Add daily job
            self.scheduler.add_job(
                self._generate_daily_summary,
                trigger=CronTrigger(hour=hour, minute=minute),
                id="daily_summary_job",
                name="Daily Summary Generation",
                max_instances=1,  # Prevent overlapping executions
                replace_existing=True,
            )

            self.scheduler.start()
            self.is_running = True
            logger.info(f"Daily summary scheduled for {summary_time} every day")

        except Exception as e:
            logger.error(f"Failed to start daily summary scheduler: {e}", exc_info=True)

    def stop(self) -> None:
        """Stop daily summary scheduling."""
        if not self.is_running:
            return

        try:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            logger.info("Daily summary manager stopped")
        except Exception as e:
            logger.error(f"Error stopping daily summary manager: {e}", exc_info=True)

    def _generate_daily_summary(self) -> None:
        """Generate summary for today (called by scheduler)."""
        try:
            today = datetime.now()
            logger.info(f"Generating daily summary for {today.date()}")

            summary = self.summary_service.generate_summary(
                date=today,
                force_regenerate=False  # Don't overwrite if already exists
            )

            if summary:
                logger.info(f"Daily summary generated successfully for {today.date()}")
            else:
                logger.warning(f"Failed to generate daily summary for {today.date()}")

        except Exception as e:
            logger.error(f"Error in daily summary generation job: {e}", exc_info=True)

    def generate_now(self, date: datetime = None) -> bool:
        """
        Manually trigger summary generation.

        Args:
            date: Date to generate summary for (default: today)

        Returns:
            True if successful, False otherwise
        """
        if date is None:
            date = datetime.now()

        try:
            logger.info(f"Manually generating summary for {date.date()}")
            summary = self.summary_service.generate_summary(
                date=date,
                force_regenerate=True  # Force regeneration
            )
            return summary is not None
        except Exception as e:
            logger.error(f"Error in manual summary generation: {e}", exc_info=True)
            return False

    def reschedule(self, new_time: str) -> bool:
        """
        Reschedule daily summary to a new time.

        Args:
            new_time: New time in HH:MM format

        Returns:
            True if successful, False otherwise
        """
        try:
            hour, minute = map(int, new_time.split(":"))

            if not self.is_running:
                logger.warning("Manager not running, starting with new schedule")
                self.start()
                return True

            # Remove existing job
            if self.scheduler.get_job("daily_summary_job"):
                self.scheduler.remove_job("daily_summary_job")

            # Add new job with new time
            self.scheduler.add_job(
                self._generate_daily_summary,
                trigger=CronTrigger(hour=hour, minute=minute),
                id="daily_summary_job",
                name="Daily Summary Generation",
                max_instances=1,
                replace_existing=True,
            )

            logger.info(f"Daily summary rescheduled to {new_time}")
            return True

        except Exception as e:
            logger.error(f"Error rescheduling daily summary: {e}", exc_info=True)
            return False
