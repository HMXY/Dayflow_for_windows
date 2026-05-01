"""OpenAI-compatible API service implementation.

Supports official OpenAI API and third-party proxy/relay services
that implement the OpenAI API interface.
"""

import logging
import base64
import json
import time
from urllib.parse import urlparse
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timedelta

from openai import OpenAI

from dayflow.analysis.llm_service import LLMService, ActivitySegment

logger = logging.getLogger(__name__)


class OpenAIService(LLMService):
    """
    OpenAI-compatible API service for video frame analysis.

    Supports both official OpenAI API and third-party proxy services
    (e.g., one-api, new-api) via configurable base_url.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o",
        base_url: Optional[str] = None,
    ):
        """
        Initialize OpenAI service.

        Args:
            api_key: OpenAI API key or third-party proxy key
            model_name: Model to use (default: gpt-4o)
            base_url: Custom API base URL for third-party proxy.
                      If None or empty, uses official OpenAI endpoint.
        """
        super().__init__(api_key)
        self.model_name = model_name
        
        if base_url and base_url.strip():
            parsed_url = urlparse(base_url.strip())
            if not parsed_url.scheme or parsed_url.scheme not in ("http", "https"):
                raise ValueError("base_url must be a valid HTTP or HTTPS URL")
            if not parsed_url.netloc:
                raise ValueError("base_url must contain a valid domain or IP")
            self.base_url = base_url.strip()
        else:
            self.base_url = None

        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
        )

        endpoint_info = self.base_url or "official OpenAI API"
        logger.info(
            f"Initialized OpenAI service with model: {model_name}, "
            f"endpoint: {endpoint_info}"
        )

    def analyze_video(
        self,
        video_path: Path,
        context: Optional[str] = None,
    ) -> List[ActivitySegment]:
        """
        Analyze video by extracting frames and sending to OpenAI vision API.

        OpenAI does not support direct video upload, so we extract frames
        and analyze them as images.

        Args:
            video_path: Path to video file
            context: Optional context from previous activities

        Returns:
            List of ActivitySegment objects
        """
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return []

        try:
            # Extract frames from video
            from dayflow.core.video_processor import VideoProcessor

            processor = VideoProcessor()
            frames_dir = video_path.parent / f"frames_{video_path.stem}"
            frames_dir.mkdir(exist_ok=True)

            frame_paths, timestamps = processor.extract_frames(
                video_path, frames_dir, interval_seconds=30
            )

            if not frame_paths:
                logger.error("No frames extracted from video")
                return []

            # Analyze frames
            return self.analyze_frames(frame_paths, timestamps, context)

        except Exception as e:
            logger.error(
                f"Error analyzing video with OpenAI: {e}", exc_info=True
            )
            return []

    def analyze_frames(
        self,
        frame_paths: List[Path],
        timestamps: List[datetime],
        context: Optional[str] = None,
    ) -> List[ActivitySegment]:
        """
        Analyze individual frames using OpenAI vision API.

        Args:
            frame_paths: List of paths to frame images
            timestamps: Corresponding timestamps for each frame
            context: Optional context from previous activities

        Returns:
            List of ActivitySegment objects
        """
        if not frame_paths or not timestamps:
            logger.error("No frames or timestamps provided")
            return []

        try:
            logger.info(
                f"Analyzing {len(frame_paths)} frames with OpenAI..."
            )

            # Build prompt
            prompt = self.get_analysis_prompt(is_video=False)
            if context:
                prompt = f"Previous context: {context}\n\n{prompt}"

            # Add timestamp information
            time_info = "\n\nFrame timestamps:\n"
            for i, ts in enumerate(timestamps):
                time_info += f"Frame {i}: {ts.strftime('%H:%M:%S')}\n"
            prompt += time_info

            # Build messages with images
            content_parts = [{"type": "text", "text": prompt}]

            # Limit to 10 frames to avoid token limits
            selected_indices = self._select_frame_indices(
                len(frame_paths), max_frames=10
            )

            for idx in selected_indices:
                if idx < len(frame_paths) and frame_paths[idx].exists():
                    image_data = self._encode_image(frame_paths[idx])
                    if image_data:
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}",
                                    "detail": "low",
                                },
                            }
                        )

            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": content_parts}],
                max_tokens=4096,
            )

            response_text = response.choices[0].message.content

            # Parse response
            activities = self._parse_frames_response(
                response_text, timestamps, len(frame_paths)
            )

            logger.info(
                f"Detected {len(activities)} activities from frames"
            )
            return activities

        except Exception as e:
            logger.error(
                f"Error analyzing frames with OpenAI: {e}", exc_info=True
            )
            return []

    def generate_text(self, prompt: str) -> str:
        """
        Generate text using OpenAI API.

        Used for daily summary generation and other text-only tasks.

        Args:
            prompt: The prompt to send

        Returns:
            Generated text response
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4096,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating text with OpenAI: {e}")
            raise

    def test_connection(self) -> bool:
        """
        Test if OpenAI service is available.

        Returns:
            True if service is available
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )
            return bool(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"OpenAI connection test failed: {e}")
            return False

    def _encode_image(self, image_path: Path) -> Optional[str]:
        """
        Encode image to base64 string.

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded string or None if failed
        """
        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to encode image {image_path}: {e}")
            return None

    def _select_frame_indices(
        self, total_frames: int, max_frames: int = 10
    ) -> List[int]:
        """
        Select evenly spaced frame indices.

        Args:
            total_frames: Total number of available frames
            max_frames: Maximum number of frames to select

        Returns:
            List of selected frame indices
        """
        if total_frames <= max_frames:
            return list(range(total_frames))

        step = total_frames / max_frames
        return [int(i * step) for i in range(max_frames)]

    def _parse_frames_response(
        self,
        response_text: str,
        timestamps: List[datetime],
        num_frames: int,
    ) -> List[ActivitySegment]:
        """
        Parse OpenAI response for frame analysis.

        Args:
            response_text: Raw response text from OpenAI
            timestamps: List of frame timestamps
            num_frames: Number of frames analyzed

        Returns:
            List of ActivitySegment objects
        """
        try:
            # Extract JSON from response
            json_start = response_text.find("[")
            json_end = response_text.rfind("]") + 1
            if json_start == -1 or json_end == 0:
                logger.error("No JSON array found in response")
                return []

            json_str = response_text[json_start:json_end]
            activities_data = json.loads(json_str)

            activities = []
            for activity_data in activities_data:
                try:
                    start_idx = int(
                        activity_data.get("start_index", 0)
                    )
                    end_idx = int(
                        activity_data.get("end_index", num_frames - 1)
                    )

                    # Clamp indices
                    start_idx = max(
                        0, min(start_idx, len(timestamps) - 1)
                    )
                    end_idx = max(
                        start_idx, min(end_idx, len(timestamps) - 1)
                    )

                    start_time = timestamps[start_idx]
                    end_time = timestamps[end_idx]

                    activity = ActivitySegment(
                        start_time=start_time,
                        end_time=end_time,
                        title=activity_data.get(
                            "title", "Untitled Activity"
                        ),
                        summary=activity_data.get("summary", ""),
                        category=self.parse_category(
                            activity_data.get("category", "Other")
                        ),
                    )
                    activities.append(activity)
                except Exception as e:
                    logger.warning(f"Failed to parse activity: {e}")

            return activities

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Response text: {response_text}")
            return []
