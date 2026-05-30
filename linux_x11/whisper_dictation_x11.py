from __future__ import annotations

import json
import queue
import re
import subprocess
import tempfile
import threading
import time
import tkinter as tk
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pyperclip
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import keyboard


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
LOG_DIR = APP_DIR / "log"


@dataclass
class AppConfig:
    hotkey: str = "ctrl+shift+space"
    model_size: str = "base.en"
    device: str = "cpu"
    compute_type: str = "int8"
    language: Optional[str] = "en"
    sample_rate: int = 16000


class RecordingOverlay:
    def __init__(self) -> None:
        self.commands: queue.Queue[object] = queue.Queue()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(timeout=2)

    def show(self) -> None:
        self.commands.put("show")

    def hide(self) -> None:
        self.commands.put("hide")

    def set_level(self, level: float) -> None:
        self.commands.put(("level", max(0.0, min(1.0, level))))

    def _run(self) -> None:
        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg="#242424")
        width = 442
        height = 87
        x = root.winfo_screenwidth() - width - 18
        y = root.winfo_screenheight() - height - 64
        root.geometry(f"{width}x{height}+{x}+{y}")

        frame = tk.Frame(root, bg="#242424", padx=14, pady=10)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Recording", fg="#ffffff", bg="#242424", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Frame(frame, bg="#242424", height=10).pack(fill="x")

        row = tk.Frame(frame, bg="#242424")
        row.pack(fill="x")
        tk.Label(row, text="+", fg="#747474", bg="#242424", font=("Segoe UI", 18)).pack(side="left")
        wave_height = 36
        wave = tk.Canvas(row, width=326, height=wave_height, bg="#242424", highlightthickness=0)
        wave.pack(side="left", padx=(12, 8), fill="x", expand=True)
        timer = tk.Label(row, text="0:00", fg="#cfcfcf", bg="#242424", font=("Segoe UI", 9))
        timer.pack(side="left")

        state = {
            "tick": 0,
            "level": 0.0,
            "levels": deque([0.0] * 112, maxlen=112),
            "started": time.monotonic(),
        }

        def animate() -> None:
            state["tick"] += 1
            state["levels"].append(state["level"])
            state["level"] *= 0.82
            wave.delete("all")
            baseline = wave_height // 2
            wave_width = int(wave.winfo_width() or 326)
            max_amplitude = baseline - 3
            levels = list(state["levels"])
            spacing = max(3, wave_width // max(1, len(levels) - 1))
            wave.create_line(0, baseline, wave_width, baseline, fill="#6f6f6f", dash=(1, 3))
            start_x = max(0, wave_width - spacing * len(levels))
            for index, sample in enumerate(levels):
                x_pos = start_x + index * spacing
                pulse = 0.82 + 0.18 * abs(((state["tick"] + index) % 18) - 9) / 9
                amplitude = min(max_amplitude, (sample ** 1.08) * max_amplitude * pulse)
                if amplitude >= 1.4:
                    wave.create_line(x_pos, baseline - amplitude, x_pos, baseline + amplitude, fill="#ffffff", width=2)
            elapsed = int(time.monotonic() - state["started"])
            timer.configure(text=f"{elapsed // 60}:{elapsed % 60:02d}")
            root.after(50, animate)

        def pump() -> None:
            while True:
                try:
                    command = self.commands.get_nowait()
                except queue.Empty:
                    break
                if command == "show":
                    state["levels"].clear()
                    state["levels"].extend([0.0] * 112)
                    state["started"] = time.monotonic()
                    root.deiconify()
                    root.lift()
                elif command == "hide":
                    root.withdraw()
                elif isinstance(command, tuple) and command[0] == "level":
                    state["level"] = command[1]
            root.after(100, pump)

        self.ready.set()
        animate()
        pump()
        root.mainloop()


class X11DictationApp:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.overlay = RecordingOverlay()
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.frames: list[np.ndarray] = []
        self.stream: Optional[sd.InputStream] = None
        self.model: Optional[WhisperModel] = None
        self.model_lock = threading.Lock()
        self.transcription_lock = threading.Lock()
        self.pressed: set[str] = set()
        self.is_recording = False
        self.lock = threading.Lock()
        self.last_level_update = 0.0

    def run(self) -> None:
        listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        listener.start()
        print(f"Whisper Dictation X11 running. Hold {self.config.hotkey} to record.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            listener.stop()

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        name = key_name(key)
        if name:
            self.pressed.add(name)
        if hotkey_pressed(self.config.hotkey, self.pressed):
            self.start_recording()

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        name = key_name(key)
        if name:
            self.pressed.discard(name)
        if self.is_recording and not hotkey_pressed(self.config.hotkey, self.pressed):
            self.stop_recording()

    def start_recording(self) -> None:
        with self.lock:
            if self.is_recording:
                return
            self.frames = []
            self.audio_queue = queue.Queue()
            self.is_recording = True
            self.overlay.show()
            self.stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=1,
                dtype="float32",
                callback=self._audio_callback,
            )
            self.stream.start()

    def stop_recording(self) -> None:
        with self.lock:
            if not self.is_recording:
                return
            self.overlay.hide()
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            while True:
                try:
                    self.frames.append(self.audio_queue.get_nowait())
                except queue.Empty:
                    break
            frames = self.frames
            self.frames = []
            self.is_recording = False
            threading.Thread(target=self._transcribe_and_paste, args=(frames,), daemon=True).start()

    def _audio_callback(self, indata: np.ndarray, _frames: int, _time_info, status) -> None:
        if status:
            print(status)
        self.audio_queue.put(indata.copy())
        now = time.monotonic()
        if now - self.last_level_update > 0.08:
            rms = float(np.sqrt(np.mean(np.square(indata))))
            self.overlay.set_level(min(1.0, (rms / 0.065) ** 0.92))
            self.last_level_update = now

    def _transcribe_and_paste(self, frames: list[np.ndarray]) -> None:
        if not frames:
            return
        audio = np.concatenate(frames, axis=0).reshape(-1)
        audio = trim_silence(audio)
        if audio.size < self.config.sample_rate // 4:
            return
        wav_path = write_temp_wav(audio, self.config.sample_rate)
        try:
            with self.transcription_lock:
                model = self._get_model()
                segments, _info = model.transcribe(
                    str(wav_path),
                    language=self.config.language,
                    vad_filter=False,
                    beam_size=5,
                )
                text = " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            wav_path.unlink(missing_ok=True)
        if not text:
            return
        append_history(text)
        paste_text(text)
        print(text)

    def _get_model(self) -> WhisperModel:
        with self.model_lock:
            if self.model is None:
                self.model = WhisperModel(
                    self.config.model_size,
                    device=self.config.device,
                    compute_type=self.config.compute_type,
                )
            return self.model


def key_name(key: keyboard.Key | keyboard.KeyCode | None) -> Optional[str]:
    if key is None:
        return None
    if isinstance(key, keyboard.KeyCode):
        return key.char.lower() if key.char else None
    raw = getattr(key, "name", str(key).replace("Key.", ""))
    aliases = {
        "ctrl_l": "ctrl",
        "ctrl_r": "ctrl",
        "shift_l": "shift",
        "shift_r": "shift",
        "cmd": "super",
        "cmd_l": "super",
        "cmd_r": "super",
    }
    return aliases.get(raw, raw)


def hotkey_pressed(hotkey: str, pressed: set[str]) -> bool:
    parts = {part.strip().lower() for part in hotkey.split("+") if part.strip()}
    return parts.issubset(pressed)


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        config = AppConfig()
        CONFIG_PATH.write_text(json.dumps(config.__dict__, indent=2) + "\n", encoding="utf-8")
        return config
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    fields = set(AppConfig.__dataclass_fields__)
    return AppConfig(**{key: value for key, value in data.items() if key in fields})


def trim_silence(audio: np.ndarray, threshold: float = 0.012, padding_ms: int = 200) -> np.ndarray:
    if audio.size == 0:
        return audio
    loud = np.abs(audio) > threshold
    if not np.any(loud):
        return audio
    first = int(np.argmax(loud))
    last = int(len(loud) - np.argmax(loud[::-1]))
    padding = int(16000 * padding_ms / 1000)
    return audio[max(0, first - padding):min(audio.size, last + padding)]


def write_temp_wav(audio: np.ndarray, sample_rate: int) -> Path:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    handle = tempfile.NamedTemporaryFile(prefix="whisper-dictation-x11-", suffix=".wav", delete=False)
    path = Path(handle.name)
    handle.close()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return path


def normalize_spacing(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def append_history(text: str) -> None:
    normalized = normalize_spacing(text)
    if not normalized:
        return
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"{time.strftime('%Y-%m-%d')}.txt"
    path.open("a", encoding="utf-8").write(f"[{time.strftime('%H:%M:%S')}] {normalized}\n\n")


def paste_text(text: str) -> None:
    pyperclip.copy(normalize_spacing(text))
    time.sleep(0.15)
    if command_exists("xdotool"):
        subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"], check=False)
    else:
        print("xdotool not found; transcript copied to clipboard but not pasted.")


def command_exists(command: str) -> bool:
    return subprocess.run(["which", command], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def main() -> None:
    X11DictationApp(load_config()).run()


if __name__ == "__main__":
    main()
