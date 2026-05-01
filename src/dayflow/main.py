"""
Dayflow Windows - Main Entry Point
"""

import sys
import logging
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt, QTimer

from dayflow.utils.logger import setup_logger
from dayflow.utils.config import Config
from dayflow.utils.security import SecureStorage
from dayflow.ui.main_window import MainWindow
from dayflow.services.system_tray import SystemTrayIcon
from dayflow.core.recorder import ScreenRecorder
from dayflow.core.storage import StorageManager
from dayflow.core.power_manager import PowerManager
from dayflow.core.video_processor import VideoProcessor
from dayflow.analysis.gemini_service import GeminiService
from dayflow.analysis.openai_service import OpenAIService
from dayflow.analysis.analysis_manager import AnalysisManager
from dayflow.services.daily_summary_manager import DailySummaryManager
from dayflow.models.database import init_db

logger = logging.getLogger(__name__)


class DayflowApp:
    """Main application coordinator."""

    def __init__(self, config: Config):
        """
        Initialize Dayflow application.

        Args:
            config: Application configuration
        """
        self.config = config
        self.recorder = None
        self.analysis_manager = None
        self.daily_summary_manager = None
        self.power_manager = None
        self.storage_manager = None

    def initialize(self) -> bool:
        """
        Initialize all application components.

        Returns:
            True if successful
        """
        try:
            logger.info("Initializing Dayflow components...")

            # Initialize database
            init_db()
            logger.info("Database initialized")

            # Initialize storage manager
            self.storage_manager = StorageManager(
                base_dir=self.config.data_dir,
                retention_days=self.config.recording.retention_days,
            )

            # Initialize AI service (if API key available)
            api_key = SecureStorage.get_api_key(self.config.analysis.provider)
            if api_key:
                provider = self.config.analysis.provider.lower()
                base_url = getattr(self.config.analysis, "api_base_url", "") or ""

                if provider == "openai":
                    llm_service = OpenAIService(
                        api_key=api_key,
                        model_name=self.config.analysis.model_name,
                        base_url=base_url if base_url.strip() else None,
                    )
                else:
                    # Default to Gemini
                    llm_service = GeminiService(
                        api_key=api_key,
                        model_name=self.config.analysis.model_name,
                    )

                # Initialize analysis manager
                self.analysis_manager = AnalysisManager(
                    llm_service=llm_service,
                    storage_manager=self.storage_manager,
                    analysis_interval_minutes=self.config.analysis.analysis_interval_minutes,
                )
                logger.info("Analysis manager initialized")
            else:
                logger.warning(
                    f"No API key found for {self.config.analysis.provider}. "
                    "Please configure in Settings."
                )

            # Initialize daily summary manager
            self.daily_summary_manager = DailySummaryManager(self.config)
            logger.info("Daily summary manager initialized")

            # Initialize screen recorder
            chunks_dir = self.storage_manager.get_chunks_dir(datetime.now())
            self.recorder = ScreenRecorder(
                output_dir=chunks_dir,
                chunk_duration=self.config.recording.chunk_duration_seconds,
                fps=self.config.recording.fps,
                on_chunk_complete=self._on_chunk_saved,
            )

            # Initialize power manager
            self.power_manager = PowerManager(
                on_sleep=self._on_system_sleep,
                on_wake=self._on_system_wake,
                on_lock=self._on_system_lock,
                on_unlock=self._on_system_unlock,
            )

            logger.info("All components initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize components: {e}", exc_info=True)
            return False

    def start(self) -> None:
        """Start all services."""
        try:
            # Start power monitoring
            if self.power_manager:
                self.power_manager.start()

            # Start recording
            if self.recorder:
                self.recorder.start()
                logger.info("Screen recording started")

            # Start analysis
            if self.analysis_manager:
                self.analysis_manager.start(run_immediately=False)
                logger.info("Analysis manager started")

            # Start daily summary scheduler
            if self.daily_summary_manager:
                self.daily_summary_manager.start()
                logger.info("Daily summary manager started")

            # Schedule cleanup
            QTimer.singleShot(60000, self._periodic_cleanup)  # Run every minute

        except Exception as e:
            logger.error(f"Error starting services: {e}", exc_info=True)

    def stop(self) -> None:
        """Stop all services."""
        try:
            logger.info("Stopping Dayflow services...")

            if self.recorder:
                self.recorder.stop()

            if self.analysis_manager:
                self.analysis_manager.stop()

            if self.daily_summary_manager:
                self.daily_summary_manager.stop()

            if self.power_manager:
                self.power_manager.stop()

            logger.info("All services stopped")

        except Exception as e:
            logger.error(f"Error stopping services: {e}", exc_info=True)

    def _on_chunk_saved(self, file_path: Path, start_time, end_time) -> None:
        """Handle recording chunk saved."""
        if self.storage_manager:
            self.storage_manager.save_chunk_record(
                file_path, start_time, end_time
            )

    def _on_system_sleep(self) -> None:
        """Handle system sleep."""
        if self.recorder:
            self.recorder.pause()

    def _on_system_wake(self) -> None:
        """Handle system wake."""
        if self.recorder:
            self.recorder.resume()

    def _on_system_lock(self) -> None:
        """Handle session lock."""
        if self.recorder:
            self.recorder.pause()

    def _on_system_unlock(self) -> None:
        """Handle session unlock."""
        if self.recorder:
            self.recorder.resume()

    def _periodic_cleanup(self) -> None:
        """Periodic cleanup task."""
        try:
            if self.storage_manager:
                self.storage_manager.cleanup_old_recordings()
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")

        # Schedule next cleanup
        QTimer.singleShot(3600000, self._periodic_cleanup)  # Every hour


def setup_application() -> QApplication:
    """Initialize and configure the Qt application."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Dayflow")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Dayflow")
    app.setQuitOnLastWindowClosed(False)  # Keep running in tray

    return app


def main() -> int:
    """Main application entry point."""
    try:
        # Setup logging
        logger = setup_logger()
        logger.info("Starting Dayflow Windows...")

        # Load configuration
        config = Config.load()
        logger.info(f"Configuration loaded from: {config.config_path}")

        # Create Qt application
        app = setup_application()

        # Initialize Dayflow app
        dayflow = DayflowApp(config)
        if not dayflow.initialize():
            QMessageBox.critical(
                None,
                "Initialization Error",
                "Failed to initialize Dayflow. Check logs for details.",
            )
            return 1

        # Create main window
        main_window = MainWindow(config)

        # Create system tray
        tray_icon = SystemTrayIcon()
        tray_icon.show_window_requested.connect(main_window.show)
        tray_icon.quit_requested.connect(app.quit)
        tray_icon.show()

        # Show main window
        main_window.show()

        # Start services
        dayflow.start()

        logger.info("Dayflow started successfully")

        # Cleanup on exit
        app.aboutToQuit.connect(dayflow.stop)

        # Run event loop
        return app.exec()

    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    from datetime import datetime  # Add missing import
    sys.exit(main())
