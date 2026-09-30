"""
Text-to-speech with Piper, running on the GPU (CUDA) when available.

Setup (once):
    pip install piper-tts sounddevice "onnxruntime-gpu[cuda,cudnn]"
    python -m piper.download_voices --download-dir voices en_US-lessac-medium

Usage:
    python tts.py "Any text to say."   # speak your own text
"""

import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime
import sounddevice as sd
from piper import PiperVoice, SynthesisConfig

VOICE_PATH = Path(__file__).parent / "voices" / "en_US-lessac-medium.onnx"

TEST_SENTENCES = [
    "Hello! I'm your bank assistant.",
    "C003 spends the most on Shopping, with a total of $2,299.98.",
    "Customer C003 had 1 failed transaction.",
    "Here are the customers in order of increasing spending: C004, C002, C001, and C003.",
]


def load_voice(voice_path: Path = VOICE_PATH, use_cuda: bool = True) -> PiperVoice:
    """Load a Piper voice, on the GPU if possible, otherwise on the CPU."""
    if not voice_path.exists():
        sys.exit(
            f"Voice model not found: {voice_path}\n"
            "Download it with: python -m piper.download_voices --download-dir voices en_US-lessac-medium"
        )
    # Hide ONNX Runtime's harmless GPU-placement warnings; real errors still show.
    onnxruntime.set_default_logger_severity(3)
    if use_cuda:
        # Load the CUDA/cuDNN DLLs installed by the nvidia-* pip packages.
        onnxruntime.preload_dlls()
    return PiperVoice.load(voice_path, use_cuda=use_cuda)


def speak(voice: PiperVoice, text: str, speed: float = 1.0) -> None:
    """
    Synthesize text and play it through the default speakers.

    Audio is streamed sentence by sentence, so playback starts as soon as the first
    sentence is ready instead of waiting for the whole text.
    speed: 1.0 is normal; higher is faster (e.g. 1.2), lower is slower.
    """
    config = SynthesisConfig(length_scale=1.0 / speed)
    stream = None
    try:
        for chunk in voice.synthesize(text, syn_config=config):
            if stream is None:
                stream = sd.OutputStream(samplerate=chunk.sample_rate, channels=1, dtype="float32")
                stream.start()
            stream.write(chunk.audio_float_array.astype(np.float32))
    finally:
        if stream is not None:
            stream.stop()  # waits for buffered audio to finish playing
            stream.close()


def main() -> None:
    start = time.perf_counter()
    voice = load_voice()
    providers = voice.session.get_providers()
    device = "GPU (CUDA)" if "CUDAExecutionProvider" in providers else "CPU"
    print(f"Loaded {VOICE_PATH.name} on {device} in {time.perf_counter() - start:.2f}s")

    sentences = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else []
    for text in sentences:
        # Time synthesis alone (no playback) to show how fast generation is.
        start = time.perf_counter()
        chunks = list(voice.synthesize(text))
        elapsed = time.perf_counter() - start
        audio_seconds = sum(len(c.audio_float_array) / c.sample_rate for c in chunks)
        print(f"\n{text}\n  synthesized {audio_seconds:.1f}s of audio in {elapsed:.3f}s")

        speak(voice, text)


if __name__ == "__main__":
    main()
