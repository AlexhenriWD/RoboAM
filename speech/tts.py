"""
speech/tts.py - Text-to-speech implementation
"""

import logging
import os
import tempfile
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)

# Optional imports
try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

try:
    from TTS.api import TTS as TTSModel
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

class TTSEngine:
    """Base class for TTS engines"""
    
    def __init__(self):
        """Initialize the TTS engine"""
        pass
    
    def speak(self, text: str, output_file: Optional[str] = None) -> Optional[str]:
        """
        Convert text to speech
        
        Args:
            text (str): Text to convert
            output_file (str, optional): Path to output file
        
        Returns:
            Optional[str]: Path to output file if written
        """
        raise NotImplementedError("Subclasses must implement speak()")
    
    def say(self, text: str) -> None:
        """
        Speak text immediately
        
        Args:
            text (str): Text to speak
        """
        raise NotImplementedError("Subclasses must implement say()")
    
    def cleanup(self) -> None:
        """Clean up resources"""
        pass


class Pyttsx3Engine(TTSEngine):
    """TTS engine using pyttsx3"""
    
    def __init__(self, voice: Optional[str] = None, rate: int = 150):
        """
        Initialize the pyttsx3 engine
        
        Args:
            voice (str, optional): Voice ID to use
            rate (int, optional): Speech rate
        """
        super().__init__()
        
        if not PYTTSX3_AVAILABLE:
            logger.error("pyttsx3 is not available")
            raise ImportError("pyttsx3 is not available")
        
        self.engine = pyttsx3.init()
        
        # Set properties
        self.engine.setProperty('rate', rate)
        
        # Set voice if specified
        if voice:
            self.engine.setProperty('voice', voice)
    
    def speak(self, text: str, output_file: Optional[str] = None) -> Optional[str]:
        """
        Convert text to speech
        
        Args:
            text (str): Text to convert
            output_file (str, optional): Path to output file
        
        Returns:
            Optional[str]: Path to output file if written
        """
        if output_file:
            self.engine.save_to_file(text, output_file)
            self.engine.runAndWait()
            return output_file
        else:
            # Create a temporary file
            fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            
            self.engine.save_to_file(text, temp_path)
            self.engine.runAndWait()
            return temp_path
    
    def say(self, text: str) -> None:
        """
        Speak text immediately
        
        Args:
            text (str): Text to speak
        """
        self.engine.say(text)
        self.engine.runAndWait()
    
    def cleanup(self) -> None:
        """Clean up resources"""
        try:
            self.engine.stop()
        except:
            pass


class CoquiTTSEngine(TTSEngine):
    """TTS engine using Coqui TTS"""
    
    def __init__(self, model_name: str = "tts_models/en/ljspeech/tacotron2-DDC"):
        """
        Initialize the Coqui TTS engine
        
        Args:
            model_name (str, optional): Name of the TTS model to use
        """
        super().__init__()
        
        if not TTS_AVAILABLE:
            logger.error("TTS is not available")
            raise ImportError("TTS is not available")
        
        self.model = TTSModel(model_name)
        logger.info(f"Loaded TTS model: {model_name}")
    
    def speak(self, text: str, output_file: Optional[str] = None) -> Optional[str]:
        """
        Convert text to speech
        
        Args:
            text (str): Text to convert
            output_file (str, optional): Path to output file
        
        Returns:
            Optional[str]: Path to output file if written
        """
        if not output_file:
            # Create a temporary file
            fd, output_file = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
        
        try:
            self.model.tts_to_file(text, file_path=output_file)
            return output_file
        except Exception as e:
            logger.error(f"Error generating speech: {e}")
            if os.path.exists(output_file):
                os.remove(output_file)
            return None
    
    def say(self, text: str) -> None:
        """
        Speak text immediately
        
        Args:
            text (str): Text to speak
        """
        output_file = self.speak(text)
        if output_file:
            # Play the file
            self._play_audio(output_file)
            # Clean up
            os.remove(output_file)
    
    def _play_audio(self, file_path: str) -> None:
        """
        Play an audio file
        
        Args:
            file_path (str): Path to audio file
        """
        try:
            import sounddevice as sd
            import soundfile as sf
            
            data, fs = sf.read(file_path)
            sd.play(data, fs)
            sd.wait()
        except ImportError:
            logger.warning("sounddevice or soundfile not available, can't play audio")
        except Exception as e:
            logger.error(f"Error playing audio: {e}")


class MockTTSEngine(TTSEngine):
    """Mock TTS engine for testing"""
    
    def __init__(self):
        """Initialize the mock TTS engine"""
        super().__init__()
        logger.warning("Using mock TTS engine")
    
    def speak(self, text: str, output_file: Optional[str] = None) -> Optional[str]:
        """
        Mock text-to-speech conversion
        
        Args:
            text (str): Text to convert
            output_file (str, optional): Path to output file
        
        Returns:
            Optional[str]: Path to output file if specified
        """
        logger.info(f"[MOCK TTS] Would speak: {text}")
        
        if output_file:
            # Create an empty file
            with open(output_file, 'w') as f:
                f.write("")
            return output_file
        
        return None
    
    def say(self, text: str) -> None:
        """
        Mock immediate speech
        
        Args:
            text (str): Text to speak
        """
        logger.info(f"[MOCK TTS] Speaking: {text}")


class TTS:
    """High-level interface for text-to-speech"""
    
    def __init__(self, engine_type: str = "auto"):
        """
        Initialize the TTS system
        
        Args:
            engine_type (str, optional): Type of TTS engine to use
                ('pyttsx3', 'coqui', 'mock', or 'auto')
        """
        self.engine = self._create_engine(engine_type)
    
    def _create_engine(self, engine_type: str) -> TTSEngine:
        """
        Create a TTS engine
        
        Args:
            engine_type (str): Type of engine to create
        
        Returns:
            TTSEngine: TTS engine instance
        """
        if engine_type == "pyttsx3" and PYTTSX3_AVAILABLE:
            return Pyttsx3Engine()
        elif engine_type == "coqui" and TTS_AVAILABLE:
            return CoquiTTSEngine()
        elif engine_type == "mock":
            return MockTTSEngine()
        elif engine_type == "auto":
            # Try to create engines in order of preference
            if TTS_AVAILABLE:
                try:
                    return CoquiTTSEngine()
                except Exception as e:
                    logger.warning(f"Failed to create Coqui TTS engine: {e}")
            
            if PYTTSX3_AVAILABLE:
                try:
                    return Pyttsx3Engine()
                except Exception as e:
                    logger.warning(f"Failed to create pyttsx3 engine: {e}")
            
            # Fall back to mock engine
            return MockTTSEngine()
        else:
            logger.warning(f"Unknown engine type: {engine_type}, using mock engine")
            return MockTTSEngine()
    
    def speak(self, text: str, output_file: Optional[str] = None) -> Optional[str]:
        """
        Convert text to speech
        
        Args:
            text (str): Text to convert
            output_file (str, optional): Path to output file
        
        Returns:
            Optional[str]: Path to output file if written
        """
        return self.engine.speak(text, output_file)
    
    def say(self, text: str) -> None:
        """
        Speak text immediately
        
        Args:
            text (str): Text to speak
        """
        self.engine.say(text)
    
    def cleanup(self) -> None:
        """Clean up resources"""
        self.engine.cleanup()


"""
speech/stt.py - Speech-to-text using Faster Whisper
"""

import logging
import os
import tempfile
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger(__name__)

# Optional imports
try:
    from faster_whisper import WhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

try:
    import pyaudio
    import wave
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False

class WhisperSTT:
    """Speech-to-text using Faster Whisper"""
    
    def __init__(
        self, 
        model_size: str = "base", 
        device: str = "cpu", 
        compute_type: str = "int8",
        download_root: Optional[str] = None
    ):
        """
        Initialize the Whisper STT model
        
        Args:
            model_size (str, optional): Size of the model to use
                ("tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3")
            device (str, optional): Device to use for computation
                ("cpu", "cuda", "auto")
            compute_type (str, optional): Compute type to use
                ("default", "auto", "int8", "int8_float16", "int16", "float16", "float32")
            download_root (str, optional): Directory to download models to
        """
        if not FASTER_WHISPER_AVAILABLE:
            logger.error("faster_whisper is not available")
            raise ImportError("faster_whisper is not available")
        
        try:
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                download_root=download_root
            )
            logger.info(f"Loaded Whisper model: {model_size} on {device}")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise
    
    def transcribe(
        self, 
        audio_file: str,
        language: Optional[str] = None,
        task: str = "transcribe",
        beam_size: int = 5,
        initial_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Transcribe an audio file
        
        Args:
            audio_file (str): Path to audio file
            language (str, optional): Language code
            task (str, optional): Task to perform ("transcribe" or "translate")
            beam_size (int, optional): Beam size for decoding
            initial_prompt (str, optional): Initial prompt for the model
        
        Returns:
            Dict[str, Any]: Transcription result
        """
        try:
            segments, info = self.model.transcribe(
                audio_file,
                language=language,
                task=task,
                beam_size=beam_size,
                initial_prompt=initial_prompt
            )
            
            segments_list = []
            full_text = ""
            
            for segment in segments:
                segments_list.append({
                    "id": segment.id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text
                })
                full_text += segment.text + " "
            
            return {
                "text": full_text.strip(),
                "segments": segments_list,
                "language": info.language,
                "language_probability": info.language_probability
            }
        
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            return {"text": "", "error": str(e)}


class AudioRecorder:
    """Records audio from microphone"""
    
    def __init__(
        self,
        channels: int = 1,
        rate: int = 16000,
        chunk: int = 1024,
        format_type: int = None  # Will be set in __init__
    ):
        """
        Initialize the audio recorder
        
        Args:
            channels (int, optional): Number of channels
            rate (int, optional): Sample rate
            chunk (int, optional): Chunk size
            format_type (int, optional): Audio format
        """
        if not PYAUDIO_AVAILABLE:
            logger.error("pyaudio is not available")
            raise ImportError("pyaudio is not available")
        
        self.channels = channels
        self.rate = rate
        self.chunk = chunk
        self.format_type = format_type or pyaudio.paInt16
        
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.recording = False
    
    def start_recording(self) -> None:
        """Start recording audio"""
        if self.recording:
            logger.warning("Already recording")
            return
        
        try:
            self.stream = self.audio.open(
                format=self.format_type,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk
            )
            
            self.frames = []
            self.recording = True
            logger.info("Started recording")
        
        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            raise
    
    def stop_recording(self) -> None:
        """Stop recording audio"""
        if not self.recording:
            logger.warning("Not recording")
            return
        
        try:
            self.stream.stop_stream()
            self.stream.close()
            self.recording = False
            logger.info("Stopped recording")
        
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            raise
    
    def read_frame(self) -> bytes:
        """
        Read a frame from the stream
        
        Returns:
            bytes: Audio frame
        """
        if not self.recording:
            logger.warning("Not recording")
            return b""
        
        try:
            return self.stream.read(self.chunk)
        
        except Exception as e:
            logger.error(f"Error reading frame: {e}")
            return b""
    
    def record(self, duration: float) -> str:
        """
        Record audio for a specified duration
        
        Args:
            duration (float): Duration in seconds
        
        Returns:
            str: Path to recorded audio file
        """
        try:
            self.start_recording()
            
            # Calculate number of chunks to record
            chunks_to_record = int(self.rate / self.chunk * duration)
            
            # Record frames
            self.frames = []
            for _ in range(chunks_to_record):
                data = self.read_frame()
                self.frames.append(data)
            
            self.stop_recording()
            
            # Create temporary file
            fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            
            # Save recording
            self.save_recording(temp_path)
            
            return temp_path
        
        except Exception as e:
            logger.error(f"Error recording audio: {e}")
            if self.recording:
                self.stop_recording()
            return ""
    
    def save_recording(self, file_path: str) -> None:
        """
        Save recording to a file
        
        Args:
            file_path (str): Path to save recording to
        """
        try:
            wf = wave.open(file_path, 'wb')
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.format_type))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.frames))
            wf.close()
            logger.info(f"Saved recording to {file_path}")
        
        except Exception as e:
            logger.error(f"Error saving recording: {e}")
            raise
    
    def close(self) -> None:
        """Clean up resources"""
        if self.recording:
            self.stop_recording()
        
        try:
            self.audio.terminate()
            logger.info("Closed audio recorder")
        
        except Exception as e:
            logger.error(f"Error closing audio recorder: {e}")


class MockSTT:
    """Mock STT for testing"""
    
    def __init__(self):
        """Initialize the mock STT"""
        logger.warning("Using mock STT")
    
    def transcribe(self, audio_file: str, **kwargs) -> Dict[str, Any]:
        """
        Mock transcription
        
        Args:
            audio_file (str): Path to audio file
            **kwargs: Additional arguments
        
        Returns:
            Dict[str, Any]: Mock transcription result
        """
        logger.info(f"[MOCK STT] Would transcribe: {audio_file}")
        
        return {
            "text": "This is a mock transcription.",
            "segments": [{
                "id": 0,
                "start": 0.0,
                "end": 1.0,
                "text": "This is a mock transcription."
            }],
            "language": "en",
            "language_probability": 1.0
        }


class MockAudioRecorder:
    """Mock audio recorder for testing"""
    
    def __init__(self, **kwargs):
        """Initialize the mock audio recorder"""
        logger.warning("Using mock audio recorder")
        self.recording = False
    
    def start_recording(self) -> None:
        """Mock start recording"""
        self.recording = True
        logger.info("[MOCK RECORDER] Started recording")
    
    def stop_recording(self) -> None:
        """Mock stop recording"""
        self.recording = False
        logger.info("[MOCK RECORDER] Stopped recording")
    
    def read_frame(self) -> bytes:
        """Mock read frame"""
        if not self.recording:
            return b""
        
        return b"\x00" * 1024
    
    def record(self, duration: float) -> str:
        """
        Mock record audio
        
        Args:
            duration (float): Duration in seconds
        
        Returns:
            str: Path to mock audio file
        """
        logger.info(f"[MOCK RECORDER] Recording for {duration} seconds")
        
        # Create a temporary file
        fd, temp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        
        # Create an empty file
        with open(temp_path, 'wb') as f:
            f.write(b"\x00" * 1024)
        
        return temp_path
    
    def save_recording(self, file_path: str) -> None:
        """Mock save recording"""
        logger.info(f"[MOCK RECORDER] Saving recording to {file_path}")
        
        # Create an empty file
        with open(file_path, 'wb') as f:
            f.write(b"\x00" * 1024)
    
    def close(self) -> None:
        """Mock close"""
        logger.info("[MOCK RECORDER] Closed")


class STT:
    """High-level interface for speech-to-text"""
    
    def __init__(self, model_size: str = "base", use_mock: bool = False):
        """
        Initialize the STT system
        
        Args:
            model_size (str, optional): Size of the model to use
            use_mock (bool, optional): Whether to use mock STT
        """
        if use_mock or not FASTER_WHISPER_AVAILABLE:
            self.model = MockSTT()
        else:
            try:
                self.model = WhisperSTT(model_size)
            except Exception as e:
                logger.warning(f"Failed to create WhisperSTT: {e}")
                self.model = MockSTT()
        
        if PYAUDIO_AVAILABLE and not use_mock:
            self.recorder_class = AudioRecorder
        else:
            self.recorder_class = MockAudioRecorder
    
    def listen(self, duration: float = 5.0) -> Dict[str, Any]:
        """
        Listen for speech and transcribe
        
        Args:
            duration (float, optional): Duration to listen for in seconds
        
        Returns:
            Dict[str, Any]: Transcription result
        """
        try:
            # Create recorder
            recorder = self.recorder_class()
            
            try:
                # Record audio
                audio_file = recorder.record(duration)
                
                # Transcribe
                if audio_file:
                    result = self.model.transcribe(audio_file)
                    
                    # Clean up
                    try:
                        os.remove(audio_file)
                    except:
                        pass
                    
                    return result
                else:
                    return {"text": "", "error": "Failed to record audio"}
            
            finally:
                # Clean up
                recorder.close()
        
        except Exception as e:
            logger.error(f"Error in listen: {e}")
            return {"text": "", "error": str(e)}
    
    def transcribe_file(self, audio_file: str) -> Dict[str, Any]:
        """
        Transcribe an audio file
        
        Args:
            audio_file (str): Path to audio file
        
        Returns:
            Dict[str, Any]: Transcription result
        """
        return self.model.transcribe(audio_file)