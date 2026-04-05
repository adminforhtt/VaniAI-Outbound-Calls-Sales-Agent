"""
Custom exceptions for ConversationManager.
Used to allow specific handling without crashing the WebSocket loop.
"""

class STTBufferException(Exception):
    """Raised when Sarvam STT returns malformed or empty buffer."""
    pass

class CampaignLoadException(Exception):
    """Raised when campaign config file is missing required keys."""
    pass

class TTSGenerationException(Exception):
    """Raised when Sarvam TTS fails to generate audio for a chunk."""
    pass

class LLMInferenceException(Exception):
    """Raised when Groq/OpenRouter inference fails or times out."""
    pass

class TwilioStreamException(Exception):
    """Raised only for fatal Twilio stream errors — will exit the loop."""
    pass
