import os
import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OfflineVoiceEngine:
    """Công cụ xử lý Giọng nói Offline (STT & TTS) với fallback an toàn."""

    def __init__(self):
        self._stt_model = None
        self._tts_model = None

    def transcribe_audio(self, audio_bytes: bytes, language: str = "vi") -> str:
        """
        Nhận diện giọng nói thành văn bản (STT) sử dụng faster-whisper.
        Tự động fallback sang chuỗi rỗng để UI dùng Web Speech API nếu chưa cài.
        """
        try:
            from faster_whisper import WhisperModel
            if self._stt_model is None:
                # Dùng model small hoặc base lượng tử hóa int8 cho CPU
                self._stt_model = WhisperModel("base", device="cpu", compute_type="int8")
            
            audio_stream = io.BytesIO(audio_bytes)
            segments, _ = self._stt_model.transcribe(audio_stream, language=language, beam_size=3)
            text = " ".join([seg.text for seg in segments]).strip()
            return text
        except ImportError:
            logger.debug("faster-whisper chưa cài đặt. Sử dụng Web Speech API native trên trình duyệt.")
            return ""
        except Exception as e:
            logger.error(f"Lỗi STT: {e}")
            return ""

    def synthesize_speech(
        self,
        text: str,
        voice: str = "vi",
        lang: str = "vi"
    ) -> Optional[bytes]:
        """
        Chuyển văn bản thành giọng nói (TTS).
        Hỗ trợ giọng tiếng Việt hoặc tiếng Anh qua Kokoro-ONNX nếu cấu hình.
        """
        if not text:
            return None

        try:
            from kokoro_onnx import Kokoro
            if self._tts_model is None:
                model_path = os.getenv("KOKORO_MODEL_PATH", "models/kokoro-v0_19.onnx")
                voices_path = os.getenv("KOKORO_VOICES_PATH", "models/voices.json")
                if os.path.exists(model_path) and os.path.exists(voices_path):
                    self._tts_model = Kokoro(model_path, voices_path)

            if self._tts_model:
                voice_name = voice if voice != "vi" else "af_sarah"
                kokoro_lang = lang if lang != "vi" else "en-us"
                samples, sample_rate = self._tts_model.create(text, voice=voice_name, speed=1.0, lang=kokoro_lang)
                import soundfile as sf
                out_buffer = io.BytesIO()
                sf.write(out_buffer, samples, sample_rate, format='WAV')
                return out_buffer.getvalue()
        except ImportError:
            logger.debug("kokoro-onnx chưa được cài đặt trong môi trường hiện tại.")
        except Exception as e:
            logger.error(f"Lỗi TTS: {e}")
        return None
