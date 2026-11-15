"""Offline text-to-speech for reading voter names aloud (Windows SAPI / WinRT).

Prefers an installed Hindi voice (e.g. Microsoft Kalpana / Hemant / Swara).
When none is installed, names are romanized ("राम प्रसाद" -> "Raam Prasaad")
so the default English voice can still pronounce them understandably.
"""

from __future__ import annotations

from voter_match.core.transliterate import devanagari_to_roman

HINDI_VOICE_HELP = (
    "हिंदी आवाज़ स्थापित नहीं है — नाम अंग्रेज़ी उच्चारण में पढ़े जा रहे हैं।\n"
    "बेहतर उच्चारण हेतु: Windows Settings → Time & Language → Language → "
    "Hindi जोड़ें → 'Speech' विकल्प डाउनलोड करें (केवल एक बार, इंटरनेट आवश्यक)।"
)


class NameSpeaker:
    """Lazy wrapper around QTextToSpeech; safe to construct when TTS is unavailable."""

    def __init__(self) -> None:
        self._tts = None
        self._initialized = False
        self.has_hindi_voice = False
        self.available = False

    def _init(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        try:
            from PySide6.QtCore import QLocale
            from PySide6.QtTextToSpeech import QTextToSpeech

            tts = QTextToSpeech()
            hindi = [v for v in tts.availableVoices() if v.locale().language() == QLocale.Language.Hindi]
            if not hindi:
                # The default engine may lack Hindi voices that another engine has
                for engine in QTextToSpeech.availableEngines():
                    if engine == "mock":
                        continue
                    alt = QTextToSpeech(engine)
                    hv = [v for v in alt.availableVoices() if v.locale().language() == QLocale.Language.Hindi]
                    if hv:
                        tts, hindi = alt, hv
                        break
            if hindi:
                tts.setLocale(hindi[0].locale())
                tts.setVoice(hindi[0])
                self.has_hindi_voice = True
            tts.setRate(-0.15)  # slightly slower for clarity
            self._tts = tts
            self.available = True
        except Exception:
            self._tts = None
            self.available = False

    def speak(self, text: str) -> bool:
        """Speak text; returns False if no speech engine is available."""
        self._init()
        if not self._tts or not text:
            return False
        try:
            self._tts.stop()
            spoken = text if self.has_hindi_voice else devanagari_to_roman(text)
            self._tts.say(spoken)
            return True
        except Exception:
            return False


_speaker: NameSpeaker | None = None


def get_speaker() -> NameSpeaker:
    global _speaker
    if _speaker is None:
        _speaker = NameSpeaker()
    return _speaker
