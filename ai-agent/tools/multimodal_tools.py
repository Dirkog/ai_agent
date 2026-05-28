"""Multimodal Tools — image, audio, video, screenshot processing
New in v6: process_image, process_audio, process_video, screenshot
"""
import os
import base64
from pathlib import Path
from typing import Optional, Dict, Any
from tools.base import BaseTool, ToolResult


class ProcessImageTool(BaseTool):
    """Анализ, редактирование, OCR изображений"""
    name = "process_image"
    description = "Analyze, OCR, or describe images using vision models"

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir)

    def execute(self, image_path: str, operation: str = "describe", prompt: str = "") -> ToolResult:
        target = self.working_dir / image_path
        if not target.exists():
            return ToolResult(success=False, error=f"Image not found: {image_path}")

        try:
            if operation == "describe":
                # Use local vision model or API
                return ToolResult(success=True, output=f"Image {image_path} ready for vision analysis. Use vision model.")
            elif operation == "ocr":
                try:
                    from PIL import Image
                    import pytesseract
                    img = Image.open(target)
                    text = pytesseract.image_to_string(img)
                    return ToolResult(success=True, output=f"OCR Result:\n{text}")
                except ImportError:
                    return ToolResult(success=False, error="pytesseract not installed. pip install pytesseract pillow")
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ProcessAudioTool(BaseTool):
    """Транскрипция, анализ аудио"""
    name = "process_audio"
    description = "Transcribe or analyze audio files (whisper, etc.)"

    def execute(self, audio_path: str, operation: str = "transcribe", language: str = "auto") -> ToolResult:
        path = Path(audio_path)
        if not path.exists():
            return ToolResult(success=False, error=f"Audio not found: {audio_path}")

        try:
            if operation == "transcribe":
                try:
                    import whisper
                    model = whisper.load_model("base")
                    result = model.transcribe(str(path), language=None if language == "auto" else language)
                    return ToolResult(success=True, output=f"Transcription:\n{result['text']}")
                except ImportError:
                    return ToolResult(success=False, error="whisper not installed. pip install openai-whisper")
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ProcessVideoTool(BaseTool):
    """Анализ кадров, описание видео"""
    name = "process_video"
    description = "Analyze video frames, extract descriptions"

    def execute(self, video_path: str, operation: str = "describe_frames", frame_interval: int = 5) -> ToolResult:
        path = Path(video_path)
        if not path.exists():
            return ToolResult(success=False, error=f"Video not found: {video_path}")

        try:
            if operation == "describe_frames":
                try:
                    import cv2
                    cap = cv2.VideoCapture(str(path))
                    frames = []
                    count = 0
                    while cap.isOpened():
                        ret, frame = cap.read()
                        if not ret:
                            break
                        if count % frame_interval == 0:
                            frames.append(f"Frame {count}: {frame.shape}")
                        count += 1
                    cap.release()
                    return ToolResult(success=True, output=f"Video analysis: {count} frames total. Key frames:\n" + "\n".join(frames[:20]))
                except ImportError:
                    return ToolResult(success=False, error="opencv-python not installed. pip install opencv-python")
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ScreenshotTool(BaseTool):
    """Скриншот экрана или элемента"""
    name = "screenshot"
    description = "Take screenshot of screen or specific element"

    def __init__(self, output_dir: str = ".ai-agent/screenshots"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, target: str = "screen", output_name: str = "screenshot.png") -> ToolResult:
        output_path = self.output_dir / output_name
        try:
            if target == "screen":
                try:
                    from PIL import ImageGrab
                    img = ImageGrab.grab()
                    img.save(output_path)
                    return ToolResult(success=True, output=f"Screenshot saved to {output_path}")
                except ImportError:
                    return ToolResult(success=False, error="Pillow not installed. pip install Pillow")
            else:
                return ToolResult(success=False, error=f"Screenshot target '{target}' not supported yet")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
