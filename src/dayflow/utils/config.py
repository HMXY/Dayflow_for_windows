"""Application configuration management."""

import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class RecordingConfig:
    """Recording configuration."""

    fps: float = 0.2  # 0.2 FPS = 1 frame per 5 seconds
    chunk_duration_seconds: int = 15
    retention_days: int = 3
    video_quality: str = "medium"  # low, medium, high
    excluded_apps: list[str] = None

    def __post_init__(self):
        if self.excluded_apps is None:
            self.excluded_apps = []


@dataclass
class AnalysisConfig:
    """AI analysis configuration."""

    provider: str = "gemini"  # gemini, ollama, openai
    model_name: str = "gemini-2.5-flash"  # Model to use for video analysis
    daily_summary_model_name: str = "gemini-2.0-flash-lite"  # Model for daily summaries
    api_base_url: str = ""  # Custom API base URL for third-party proxy/relay
    analysis_interval_minutes: int = 15
    context_window_minutes: int = 60
    auto_categorize: bool = True
    auto_daily_summary: bool = True  # Enable automatic daily summary
    daily_summary_time: str = "22:00"  # Time to generate daily summary (HH:MM)


@dataclass
class UIConfig:
    """UI preferences."""

    theme: str = "light"  # light, dark
    language: str = "en"
    show_notifications: bool = True
    minimize_to_tray: bool = True


@dataclass
class Config:
    """Main application configuration."""

    recording: RecordingConfig
    analysis: AnalysisConfig
    ui: UIConfig
    config_path: Path
    data_dir: Path

    @classmethod
    def get_default_paths(cls) -> tuple[Path, Path]:
        """Get default configuration and data directory paths."""
        app_data = Path.home() / "AppData" / "Local" / "Dayflow"
        app_data.mkdir(parents=True, exist_ok=True)

        config_path = app_data / "config.json"
        data_dir = app_data / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        return config_path, data_dir

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """
        Load configuration from file or create default.

        Args:
            config_path: Optional custom config path

        Returns:
            Config instance
        """
        default_config_path, data_dir = cls.get_default_paths()

        if config_path is None:
            config_path = default_config_path

        if config_path.exists():
            with open(config_path, "r") as f:
                data = json.load(f)

            return cls(
                recording=RecordingConfig(**data.get("recording", {})),
                analysis=AnalysisConfig(**data.get("analysis", {})),
                ui=UIConfig(**data.get("ui", {})),
                config_path=config_path,
                data_dir=data_dir,
            )
        else:
            # Create default config
            config = cls(
                recording=RecordingConfig(),
                analysis=AnalysisConfig(),
                ui=UIConfig(),
                config_path=config_path,
                data_dir=data_dir,
            )
            config.save()
            return config

    def save(self) -> None:
        """Save configuration to file."""
        data = {
            "recording": asdict(self.recording),
            "analysis": asdict(self.analysis),
            "ui": asdict(self.ui),
        }

        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key."""
        parts = key.split(".")
        obj = self

        try:
            for part in parts:
                obj = getattr(obj, part)
            return obj
        except AttributeError:
            return default

    def set(self, key: str, value: Any) -> None:
        """Set configuration value by dot-notation key."""
        parts = key.split(".")
        obj = self

        for part in parts[:-1]:
            obj = getattr(obj, part)

        setattr(obj, parts[-1], value)
        self.save()
