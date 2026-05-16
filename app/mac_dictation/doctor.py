from __future__ import annotations

import argparse
import platform
import time
from array import array


def measure_microphone_peak(seconds: float = 5.0, sample_rate: int = 16_000) -> int:
    import sounddevice as sd

    peak = 0

    def callback(indata, frames, time_info, status):  # pragma: no cover - manual macOS diagnostic
        nonlocal peak
        if status:
            print(f"status: {status}", flush=True)
        samples = array("h")
        samples.frombytes(bytes(indata))
        if samples:
            peak = max(peak, max(abs(sample) for sample in samples))

    print(f"Python: {platform.python_version()}")
    print(f"Input device: {sd.query_devices(kind='input')}")
    print(f"Recording for {seconds:.1f} seconds. Speak loudly now...")
    stream = sd.RawInputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        callback=callback,
    )
    stream.start()
    time.sleep(seconds)
    stream.stop()
    stream.close()
    print(f"peak: {peak}")
    if peak <= 0:
        print("Result: microphone opened but captured silence. Check macOS Microphone permission/input device.")
    elif peak < 100:
        print("Result: microphone captured very quiet audio. Try speaking closer/louder or check input level.")
    else:
        print("Result: microphone capture looks alive.")
    return peak


def main() -> None:
    parser = argparse.ArgumentParser(description="WhisperType local diagnostics")
    parser.add_argument("--seconds", type=float, default=5.0, help="Seconds to record for the microphone test")
    args = parser.parse_args()
    measure_microphone_peak(seconds=args.seconds)


if __name__ == "__main__":
    main()
