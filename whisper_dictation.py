from __future__ import annotations

import ctypes
import json
import msvcrt
import os
import queue
import re
import sys
import tempfile
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
import wave
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pyautogui
import pyperclip
import pystray
import sounddevice as sd
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw
from pynput import keyboard


if getattr(sys, "frozen", False):
    EXE_DIR = Path(sys.executable).resolve().parent
    APP_DIR = EXE_DIR.parent.parent if EXE_DIR.parent.name.lower() == "app" else EXE_DIR
else:
    APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
ENV_PATH = APP_DIR / ".env"
LOCK_PATH = APP_DIR / "whisper_dictation.lock"
LOG_PATH = APP_DIR / "whisper_dictation.log"
TRANSCRIPT_LOG_DIR = APP_DIR / "log"


@dataclass
class AppConfig:
    hotkey: str = "<ctrl>+<shift>+space"
    cancel_key: str = "esc"
    model_size: str = "base.en"
    device: str = "cpu"
    compute_type: str = "int8"
    language: Optional[str] = "en"
    paste_method: str = "clipboard"
    restore_clipboard: bool = False
    sample_rate: int = 16000
    silence_trim: bool = True
    visual_indicator: bool = True
    cleanup_mode: str = "clean"
    cleanup_engine: str = "ollama"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_base_url: str = "http://localhost:11434"
    openai_model: str = "gpt-4.1-nano"
    openai_base_url: str = "https://api.openai.com/v1"


class Status:
    IDLE = "Idle"
    RECORDING = "Recording"
    RECORDING_AND_PROCESSING = "Recording + Processing"
    PROCESSING = "Processing"


class SingleInstance:
    def __init__(self, path: Path) -> None:
        self.handle = path.open("a+b")
        self.handle.seek(0)
        try:
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.handle.close()
            raise RuntimeError("Whisper Dictation is already running.")

    def release(self) -> None:
        try:
            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.handle.close()


class RecordingIndicator:
    def __init__(self) -> None:
        self.commands: queue.Queue[Any] = queue.Queue()
        self.ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.ready.wait(timeout=2)

    def show(self, title: str = "Recording") -> None:
        self.commands.put(("show", title))

    def hide(self) -> None:
        self.commands.put("hide")

    def set_title(self, title: str) -> None:
        self.commands.put(("title", title))

    def set_level(self, level: float) -> None:
        self.commands.put(("level", max(0.0, min(1.0, level))))

    def open_settings(self, app: "DictationApp") -> None:
        self.commands.put(("settings", app))

    def stop(self) -> None:
        self.commands.put("stop")

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

        title_label = tk.Label(
            frame,
            text="Recording",
            fg="#ffffff",
            bg="#242424",
            font=("Segoe UI", 10, "bold"),
        )
        title_label.pack(anchor="w")

        spacer = tk.Frame(frame, bg="#242424", height=10)
        spacer.pack(fill="x")

        row = tk.Frame(frame, bg="#242424")
        row.pack(fill="x", pady=(0, 0))

        tk.Label(row, text="+", fg="#747474", bg="#242424", font=("Segoe UI", 18)).pack(side="left")

        wave_height = 36
        wave = tk.Canvas(row, width=326, height=wave_height, bg="#242424", highlightthickness=0)
        wave.pack(side="left", padx=(12, 8), fill="x", expand=True)

        timer_label = tk.Label(row, text="0:00", fg="#cfcfcf", bg="#242424", font=("Segoe UI", 9))
        timer_label.pack(side="left", padx=(0, 0))

        state = {
            "tick": 0,
            "level": 0.0,
            "levels": deque([0.0] * 112, maxlen=112),
            "started": time.monotonic(),
            "settings": None,
        }

        def animate() -> None:
            state["tick"] += 1
            level = state["level"]
            state["levels"].append(level)
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
                visual_level = min(1.0, sample)
                shaped_level = visual_level ** 1.08
                amplitude = min(max_amplitude, shaped_level * max_amplitude * pulse)
                if amplitude < 1.4:
                    continue
                wave.create_line(x_pos, baseline - amplitude, x_pos, baseline + amplitude, fill="#ffffff", width=2)

            elapsed = int(time.monotonic() - state["started"])
            timer_label.configure(text=f"{elapsed // 60}:{elapsed % 60:02d}")
            root.after(50, animate)

        def pump() -> None:
            while True:
                try:
                    command = self.commands.get_nowait()
                except queue.Empty:
                    break
                if isinstance(command, tuple) and command[0] == "show":
                    title_label.configure(text=command[1])
                    state["levels"].clear()
                    state["levels"].extend([0.0] * 112)
                    state["level"] = 0.0
                    state["started"] = time.monotonic()
                    show_without_activation(root)
                elif command == "hide":
                    root.withdraw()
                elif command == "stop":
                    root.destroy()
                    return
                elif isinstance(command, tuple) and command[0] == "title":
                    title_label.configure(text=command[1])
                    state["started"] = time.monotonic()
                elif isinstance(command, tuple) and command[0] == "level":
                    state["level"] = command[1]
                elif isinstance(command, tuple) and command[0] == "settings":
                    state["settings"] = open_settings_window(root, command[1], state["settings"])
            root.after(100, pump)

        self.ready.set()
        make_no_activate(root)
        animate()
        pump()
        root.mainloop()


class DictationApp:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.status = Status.IDLE
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.frames: list[np.ndarray] = []
        self.stream: Optional[sd.InputStream] = None
        self.target_hwnd: Optional[int] = None
        self.is_recording = False
        self.active_jobs = 0
        self.worker_threads: list[threading.Thread] = []
        self.model: Optional[WhisperModel] = None
        self.model_lock = threading.Lock()
        self.transcription_lock = threading.Lock()
        self.icon: Optional[pystray.Icon] = None
        self.indicator: Optional[RecordingIndicator] = RecordingIndicator() if config.visual_indicator else None
        self.last_level_update = 0.0
        self.cancel_requested = False
        self.release_poll_active = False
        self.ollama_notice_shown = False
        self.openai_notice_shown = False
        self.processing_stage = ""
        self.lock = threading.Lock()

    def run(self) -> None:
        self.icon = pystray.Icon(
            "whisper-dictation",
            self._make_icon("idle"),
            "Whisper Dictation",
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: f"Status: {self.status}", None, enabled=False),
                pystray.MenuItem(lambda item: f"Mode: {self._mode_label()}", None, enabled=False),
                pystray.MenuItem(lambda item: f"Cleanup: {self.config.cleanup_mode.title()}", None, enabled=False),
                pystray.MenuItem(lambda item: f"Engine: {self._cleanup_engine_label()}", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Settings", self._open_settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Raw", self._use_raw_cleanup, checked=lambda item: self.config.cleanup_mode == "raw"),
                pystray.MenuItem("Clean", self._use_clean_cleanup, checked=lambda item: self.config.cleanup_mode == "clean"),
                pystray.MenuItem("Enhanced", self._use_enhanced_cleanup, checked=lambda item: self.config.cleanup_mode == "enhanced"),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Use OpenAI Cleanup", self._use_openai_cleanup, checked=lambda item: self.config.cleanup_engine == "openai"),
                pystray.MenuItem("Use Ollama Cleanup", self._use_ollama_cleanup, checked=lambda item: self.config.cleanup_engine == "ollama"),
                pystray.MenuItem("Open API Key File", self._open_env_file),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Use GPU", self._use_gpu, checked=lambda item: self.config.device == "cuda"),
                pystray.MenuItem("Use CPU", self._use_cpu, checked=lambda item: self.config.device == "cpu"),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open History", self._open_history),
                pystray.MenuItem("Open Logs Folder", self._open_logs),
                pystray.MenuItem("Quit", self._quit),
            ),
        )

        hotkey = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
        hotkey.start()

        print(f"Whisper Dictation is running. Hold hotkey: {self.config.hotkey}")
        self.icon.run()
        if self.indicator is not None:
            self.indicator.stop()
        hotkey.stop()

    def start_recording(self) -> None:
        with self.lock:
            if self.is_recording:
                return
            self._start_recording_locked()

    def stop_recording(self) -> None:
        with self.lock:
            if not self.is_recording:
                return
            self._stop_recording_locked()

    def cancel_recording(self) -> None:
        with self.lock:
            if not self.is_recording:
                return
            self.cancel_requested = True
            self._stop_recording_locked()

    def _open_logs(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        TRANSCRIPT_LOG_DIR.mkdir(exist_ok=True)
        os.startfile(TRANSCRIPT_LOG_DIR)

    def _open_history(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        open_latest_history()

    def _open_settings(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        if self.indicator is not None:
            self.indicator.open_settings(self)
        else:
            def launch() -> None:
                window = open_settings_window(None, self, None)
                window.mainloop()

            threading.Thread(target=launch, daemon=True).start()

    def _mode_label(self) -> str:
        return "GPU" if self.config.device == "cuda" else "CPU"

    def _cleanup_engine_label(self) -> str:
        return "OpenAI" if self.config.cleanup_engine == "openai" else "Ollama" if self.config.cleanup_engine == "ollama" else "Off"

    def _use_raw_cleanup(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._set_cleanup_mode("raw")

    def _use_clean_cleanup(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._set_cleanup_mode("clean")

    def _use_enhanced_cleanup(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._set_cleanup_mode("enhanced")

    def _set_cleanup_mode(self, mode: str) -> None:
        self.config.cleanup_mode = mode
        save_config(self.config)
        log_event(f"cleanup mode set to {mode}")
        if self.icon is not None:
            self.icon.update_menu()

    def _use_openai_cleanup(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._set_cleanup_engine("openai")

    def _use_ollama_cleanup(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._set_cleanup_engine("ollama")

    def _set_cleanup_engine(self, engine: str) -> None:
        self.config.cleanup_engine = engine
        save_config(self.config)
        log_event(f"cleanup engine set to {engine}")
        if self.icon is not None:
            self.icon.update_menu()

    def apply_settings(self, updates: dict[str, Any]) -> None:
        old_device = self.config.device
        old_compute_type = self.config.compute_type
        for key, value in updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        if self.config.device != old_device or self.config.compute_type != old_compute_type:
            with self.model_lock:
                self.model = None
        save_config(self.config)
        log_event("settings updated")
        if self.icon is not None:
            self.icon.update_menu()

    def _open_env_file(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        ensure_env_file()
        os.startfile(ENV_PATH)

    def _use_gpu(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._set_compute_mode("cuda", "float16")

    def _use_cpu(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self._set_compute_mode("cpu", "int8")

    def _set_compute_mode(self, device: str, compute_type: str) -> None:
        with self.model_lock:
            self.config.device = device
            self.config.compute_type = compute_type
            self.model = None
            save_config(self.config)
        log_event(f"compute mode set to {device}/{compute_type}")
        if self.icon is not None:
            self.icon.update_menu()

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if hotkey_is_down(self.config.hotkey):
            self.start_recording()
            if sys.platform == "win32" and not self.release_poll_active:
                self.release_poll_active = True
                threading.Thread(target=self._poll_hotkey_release, daemon=True).start()
        elif key_matches(key, self._cancel_hotkey()):
            self.cancel_recording()

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if sys.platform != "win32" and not hotkey_is_down(self.config.hotkey):
            self.stop_recording()

    def _poll_hotkey_release(self) -> None:
        try:
            while hotkey_is_down(self.config.hotkey):
                time.sleep(0.035)
            self.stop_recording()
        finally:
            self.release_poll_active = False

    def _start_recording_locked(self) -> None:
        self.frames = []
        self.cancel_requested = False
        self.audio_queue = queue.Queue()
        self.target_hwnd = get_foreground_window()
        self.is_recording = True
        self._refresh_status_locked()
        self._update_icon("recording")
        if self.indicator is not None:
            self.indicator.show()

        self.stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
        )
        self.stream.start()
        print("Recording...")

    def _stop_recording_locked(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None

        while True:
            try:
                self.frames.append(self.audio_queue.get_nowait())
            except queue.Empty:
                break

        self.is_recording = False
        if self.cancel_requested:
            if self.indicator is not None:
                self.indicator.hide()
            self._refresh_status_locked()
            self._update_icon("busy" if self.active_jobs else "idle")
            print("Recording canceled.")
            return

        frames = self.frames
        target_hwnd = self.target_hwnd
        self.frames = []
        self.target_hwnd = None
        self.active_jobs += 1
        self.processing_stage = "Transcribing"
        self._refresh_status_locked()
        self._update_icon("busy")
        if self.indicator is not None and not self.is_recording:
            self.indicator.show("Transcribing")
        worker = threading.Thread(target=self._transcribe_and_paste, args=(frames, target_hwnd), daemon=True)
        self.worker_threads.append(worker)
        worker.start()

    def _audio_callback(self, indata: np.ndarray, _frames: int, _time_info, status) -> None:
        if status:
            print(status, file=sys.stderr)
        self.audio_queue.put(indata.copy())
        if self.indicator is not None:
            now = time.monotonic()
            if now - self.last_level_update > 0.08:
                rms = float(np.sqrt(np.mean(np.square(indata))))
                self.indicator.set_level(min(1.0, (rms / 0.065) ** 0.92))
                self.last_level_update = now

    def _transcribe_and_paste(self, frames: list[np.ndarray], target_hwnd: Optional[int]) -> None:
        try:
            if not frames:
                print("No audio captured.")
                return

            audio = np.concatenate(frames, axis=0).reshape(-1)
            if self.config.silence_trim:
                audio = trim_silence(audio)

            if audio.size < self.config.sample_rate // 4:
                print("Audio was too short to transcribe.")
                log_event("audio too short to transcribe")
                return

            wav_path = write_temp_wav(audio, self.config.sample_rate)
            try:
                with self.transcription_lock:
                    self._set_processing_stage("Transcribing")
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
                print("No speech detected.")
                log_event("no speech detected")
                return

            self._set_processing_stage("Cleaning")
            output_text = self._cleanup_text(text)
            append_transcript_history(text, output_text, self.config.cleanup_mode)
            self._set_processing_stage("Pasting")
            paste_text(output_text, target_hwnd=target_hwnd, restore_clipboard=self.config.restore_clipboard)
            print(f"Pasted: {output_text}")
        except Exception as exc:
            print(f"Dictation failed: {exc}", file=sys.stderr)
            log_event(f"dictation failed: {exc}")
        finally:
            with self.lock:
                self.active_jobs = max(0, self.active_jobs - 1)
                if self.active_jobs == 0:
                    self.processing_stage = ""
                    if self.indicator is not None and not self.is_recording:
                        self.indicator.hide()
                self._refresh_status_locked()
                self._update_icon("recording" if self.is_recording else "busy" if self.active_jobs else "idle")

    def _get_model(self) -> WhisperModel:
        with self.model_lock:
            if self.model is None:
                print(f"Loading Whisper model: {self.config.model_size} ({self.config.device}/{self.config.compute_type})")
                try:
                    self.model = WhisperModel(
                        self.config.model_size,
                        device=self.config.device,
                        compute_type=self.config.compute_type,
                    )
                except Exception as exc:
                    if self.config.device != "cuda":
                        raise
                    log_event(f"gpu model load failed, falling back to cpu/int8: {exc}")
                    self.config.device = "cpu"
                    self.config.compute_type = "int8"
                    save_config(self.config)
                    self.model = WhisperModel(
                        self.config.model_size,
                        device=self.config.device,
                        compute_type=self.config.compute_type,
                    )
                    if self.icon is not None:
                        self.icon.update_menu()
            return self.model

    def _cleanup_text(self, text: str) -> str:
        if self.config.cleanup_mode == "raw" or self.config.cleanup_engine == "off":
            return text
        if self.config.cleanup_engine == "openai":
            try:
                return cleanup_with_openai(
                    text=text,
                    mode=self.config.cleanup_mode,
                    model=self.config.openai_model,
                    base_url=self.config.openai_base_url,
                )
            except OpenAIUnavailableError as exc:
                log_event(f"openai cleanup unavailable, using raw transcript: {exc}")
                if not self.openai_notice_shown:
                    self.openai_notice_shown = True
                    notify_user(
                        "Whisper Dictation: OpenAI API Key Required",
                        "OpenAI cleanup requires OPENAI_API_KEY in the .env file.\n\n"
                        "Use the tray menu option 'Open API Key File', add your key, then restart the app.\n\n"
                        "For now, raw transcripts will be pasted.",
                    )
                return text
            except Exception as exc:
                log_event(f"openai cleanup failed, using raw transcript: {exc}")
                return text
        if self.config.cleanup_engine != "ollama":
            return text
        try:
            return cleanup_with_ollama(
                text=text,
                mode=self.config.cleanup_mode,
                model=self.config.ollama_model,
                base_url=self.config.ollama_base_url,
                on_model_missing=lambda _model: self._set_processing_stage("Model missing, downloading now"),
            )
        except OllamaUnavailableError as exc:
            log_event(f"ollama unavailable, using raw transcript: {exc}")
            if not self.ollama_notice_shown:
                self.ollama_notice_shown = True
                notify_user(
                    "Whisper Dictation: Ollama Required",
                    "Clean and Enhanced modes require Ollama.\n\n"
                    "Install Ollama from https://ollama.com/download, then restart or keep using Raw mode.\n\n"
                    "For now, raw transcripts will be pasted.",
                )
            return text
        except Exception as exc:
            log_event(f"cleanup failed, using raw transcript: {exc}")
            return text

    def _set_processing_stage(self, stage: str) -> None:
        with self.lock:
            if not self.active_jobs:
                return
            self.processing_stage = stage
            if self.indicator is not None and not self.is_recording:
                self.indicator.show(stage)
            self._refresh_status_locked()
            self._update_icon("busy")

    def _cancel_hotkey(self) -> str:
        key = self.config.cancel_key.strip().lower()
        return key if key.startswith("<") else f"<{key}>"

    def _quit(self, icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        with self.lock:
            if self.stream is not None:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            if self.indicator is not None:
                self.indicator.stop()
        icon.stop()

    def _refresh_status_locked(self) -> None:
        if self.is_recording and self.active_jobs:
            self.status = Status.RECORDING_AND_PROCESSING
        elif self.is_recording:
            self.status = Status.RECORDING
        elif self.active_jobs:
            self.status = self.processing_stage or Status.PROCESSING
        else:
            self.status = Status.IDLE

    def _update_icon(self, state: str) -> None:
        if self.icon is not None:
            self.icon.icon = self._make_icon(state)
            self.icon.title = f"Whisper Dictation - {self.status}"

    @staticmethod
    def _make_icon(state: str) -> Image.Image:
        color = {
            "idle": (38, 132, 255),
            "recording": (220, 53, 69),
            "busy": (255, 193, 7),
        }.get(state, (38, 132, 255))

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill=color)
        draw.rounded_rectangle((27, 16, 37, 39), radius=5, fill=(255, 255, 255))
        draw.arc((20, 29, 44, 53), 0, 180, fill=(255, 255, 255), width=4)
        draw.line((32, 51, 32, 58), fill=(255, 255, 255), width=4)
        return image


def key_matches(key: keyboard.Key | keyboard.KeyCode | None, configured: str) -> bool:
    name = normalize_hotkey_part(configured)
    if key is None:
        return False
    if isinstance(key, keyboard.KeyCode):
        return key.char is not None and key.char.lower() == name
    key_name = key_to_name(key)
    return key_name == name


def normalize_hotkey_part(part: str) -> str:
    name = part.strip().lower().removeprefix("<").removesuffix(">")
    aliases = {
        "control": "ctrl",
        "ctrl_l": "ctrl",
        "ctrl_r": "ctrl",
        "shift_l": "shift",
        "shift_r": "shift",
        "cmd": "win",
        "cmd_l": "win",
        "cmd_r": "win",
        "win_l": "win",
        "win_r": "win",
        "escape": "esc",
    }
    return aliases.get(name, name)


def parse_hotkey(configured: str) -> list[str]:
    return [normalize_hotkey_part(part) for part in configured.split("+") if part.strip()]


def key_to_name(key: keyboard.Key | keyboard.KeyCode | None) -> Optional[str]:
    if key is None:
        return None
    if isinstance(key, keyboard.KeyCode):
        return key.char.lower() if key.char else None
    raw = getattr(key, "name", str(key).replace("Key.", ""))
    return normalize_hotkey_part(raw)


def hotkey_is_down(configured: str) -> bool:
    parts = parse_hotkey(configured)
    if not parts:
        return False
    if sys.platform != "win32":
        return False
    return all(is_key_down(vk) for part in parts for vk in hotkey_virtual_keys(part))


def hotkey_virtual_keys(part: str) -> list[int]:
    name = normalize_hotkey_part(part)
    if name.startswith("f") and name[1:].isdigit():
        number = int(name[1:])
        if 1 <= number <= 24:
            return [0x6F + number]
    if len(name) == 1:
        return [ord(name.upper())]
    special = {
        "ctrl": [0x11],
        "shift": [0x10],
        "alt": [0x12],
        "win": [0x5B, 0x5C],
        "space": [0x20],
        "esc": [0x1B],
        "tab": [0x09],
        "enter": [0x0D],
    }
    return special.get(name, [])


def is_key_down(virtual_key: int) -> bool:
    if sys.platform != "win32":
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)


def make_no_activate(root: tk.Tk) -> None:
    if sys.platform != "win32":
        return
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    if not hwnd:
        hwnd = root.winfo_id()
    gwl_exstyle = -20
    ws_ex_toolwindow = 0x00000080
    ws_ex_noactivate = 0x08000000
    style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
    ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, style | ws_ex_toolwindow | ws_ex_noactivate)
    apply_rounded_corners(hwnd)


def apply_rounded_corners(hwnd: int) -> None:
    try:
        dwmwa_window_corner_preference = 33
        dwmwcp_round = 2
        preference = ctypes.c_int(dwmwcp_round)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            dwmwa_window_corner_preference,
            ctypes.byref(preference),
            ctypes.sizeof(preference),
        )
    except Exception:
        pass


def show_without_activation(root: tk.Tk) -> None:
    if sys.platform != "win32":
        root.deiconify()
        root.lift()
        return

    root.deiconify()
    root.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    if not hwnd:
        hwnd = root.winfo_id()
    hwnd_topmost = -1
    swp_noactivate = 0x0010
    swp_showwindow = 0x0040
    sw_shownoactivate = 4
    ctypes.windll.user32.ShowWindow(hwnd, sw_shownoactivate)
    ctypes.windll.user32.SetWindowPos(hwnd, hwnd_topmost, 0, 0, 0, 0, swp_noactivate | swp_showwindow | 0x0001 | 0x0002)


class OllamaUnavailableError(RuntimeError):
    pass


class OpenAIUnavailableError(RuntimeError):
    pass


def cleanup_with_openai(text: str, mode: str, model: str, base_url: str) -> str:
    api_key = get_env_value("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIUnavailableError("OPENAI_API_KEY is missing")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": cleanup_instruction(mode)},
            {"role": "user", "content": text.strip()},
        ],
        "temperature": 0.1,
        "max_tokens": 700 if mode == "enhanced" else 350,
    }
    data = openai_request(base_url, "/chat/completions", payload, api_key, timeout=45)
    choices = data.get("choices", [])
    if not choices:
        return text
    message = choices[0].get("message", {})
    cleaned = normalize_output_text(str(message.get("content", "")))
    return cleaned or text


def openai_request(base_url: str, path: str, payload: dict, api_key: str, timeout: int) -> dict:
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OpenAIUnavailableError(f"OpenAI API error {exc.code}: {body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise OpenAIUnavailableError(str(exc)) from exc
    return json.loads(body) if body else {}


def cleanup_with_ollama(
    text: str,
    mode: str,
    model: str,
    base_url: str,
    on_model_missing: Optional[Callable[[str], None]] = None,
) -> str:
    if not ollama_is_available(base_url):
        raise OllamaUnavailableError("Ollama API is not reachable")
    ensure_ollama_model(model, base_url, on_model_missing=on_model_missing)
    prompt = cleanup_prompt(text, mode)
    response = ollama_generate(prompt, model, base_url, mode)
    cleaned = normalize_output_text(response)
    return cleaned or text


def ollama_is_available(base_url: str) -> bool:
    try:
        ollama_request(base_url, "/api/tags", None, timeout=2)
        return True
    except Exception:
        return False


def ensure_ollama_model(
    model: str,
    base_url: str,
    on_model_missing: Optional[Callable[[str], None]] = None,
) -> None:
    tags = ollama_request(base_url, "/api/tags", None, timeout=10)
    models = {item.get("name") for item in tags.get("models", [])}
    if model in models:
        return
    log_event(f"pulling ollama model {model}")
    if on_model_missing is not None:
        on_model_missing(model)
    ollama_request(base_url, "/api/pull", {"name": model, "stream": False}, timeout=1800)
    log_event(f"ollama model ready {model}")


def ollama_generate(prompt: str, model: str, base_url: str, mode: str) -> str:
    predict_limit = 700 if mode == "enhanced" else 350
    data = ollama_request(
        base_url,
        "/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",
            "options": {
                "temperature": 0.1,
                "num_predict": predict_limit,
            },
        },
        timeout=300,
    )
    return str(data.get("response", "")).strip()


def ollama_request(base_url: str, path: str, payload: Optional[dict], timeout: int) -> dict:
    url = base_url.rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise OllamaUnavailableError(str(exc)) from exc
    return json.loads(body) if body else {}


def cleanup_prompt(text: str, mode: str) -> str:
    return f"{cleanup_instruction(mode)}\n\nTranscript:\n{text.strip()}"


def cleanup_instruction(mode: str) -> str:
    if mode == "enhanced":
        instruction = (
            "Rewrite the transcript into polished, clear text. Preserve the meaning, keep technical terms, "
            "remove filler words or false starts, and improve clarity without adding facts. Use short paragraphs by "
            "default, but use bullet points when the speaker is listing tasks, options, steps, requirements, or "
            "multiple distinct ideas."
        )
    else:
        instruction = (
            "Clean up the transcript. Fix punctuation and casing, remove filler words and repeated false starts, "
            "but preserve the speaker's meaning and wording as much as possible. Do not summarize. Keep normal prose "
            "by default, but use bullet points when the transcript clearly contains a list of tasks, options, steps, "
            "requirements, or multiple distinct ideas."
        )
    return (
        f"{instruction}\n\n"
        "Return only the final text. No commentary, labels, or quotes. If you use bullets, start each bullet with '- '."
    )


def notify_user(title: str, message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    else:
        print(f"{title}: {message}")


def get_foreground_window() -> Optional[int]:
    if sys.platform != "win32":
        return None
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    return int(hwnd) if hwnd else None


def restore_foreground_window(hwnd: Optional[int]) -> None:
    if sys.platform != "win32" or not hwnd:
        return
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return
    user32.ShowWindow(hwnd, 5)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.12)


def send_ctrl_v() -> None:
    if sys.platform != "win32":
        pyautogui.hotkey("ctrl", "v", interval=0.03)
        return
    user32 = ctypes.windll.user32
    vk_control = 0x11
    vk_v = 0x56
    keyeventf_keyup = 0x0002
    user32.keybd_event(vk_control, 0, 0, 0)
    user32.keybd_event(vk_v, 0, 0, 0)
    time.sleep(0.03)
    user32.keybd_event(vk_v, 0, keyeventf_keyup, 0)
    user32.keybd_event(vk_control, 0, keyeventf_keyup, 0)


def log_event(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"[{timestamp}] {message}\n")


def append_transcript_history(raw_text: str, output_text: Optional[str] = None, mode: str = "raw") -> None:
    raw = normalize_spacing(raw_text)
    output = normalize_output_text(output_text) if output_text is not None else raw
    if not raw:
        return
    TRANSCRIPT_LOG_DIR.mkdir(exist_ok=True)
    log_path = TRANSCRIPT_LOG_DIR / f"{time.strftime('%Y-%m-%d')}.txt"
    timestamp = time.strftime("%H:%M:%S")
    with log_path.open("a", encoding="utf-8") as log:
        if output != raw:
            log.write(f"[{timestamp}] {mode.upper()}\nRAW: {raw}\nOUTPUT: {output}\n\n")
        else:
            log.write(f"[{timestamp}] {raw}\n\n")


def open_latest_history() -> None:
    TRANSCRIPT_LOG_DIR.mkdir(exist_ok=True)
    latest = sorted(TRANSCRIPT_LOG_DIR.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not latest:
        notify_user("Whisper Dictation", "No dictation history yet.")
        return
    try:
        os.startfile(latest[0])
    except OSError as exc:
        log_event(f"failed to open history file: {exc}")
        notify_user("Whisper Dictation", f"Could not open history file:\n{latest[0]}")


def open_settings_window(parent: Optional[tk.Tk], app: DictationApp, existing: Optional[tk.Toplevel]) -> tk.Toplevel:
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        existing.focus_force()
        return existing

    window = tk.Toplevel(parent) if parent is not None else tk.Tk()
    window.title("Whisper Dictation Settings")
    window.geometry("460x560")
    window.resizable(False, False)
    window.configure(bg="#1f1f1f")

    try:
        window.iconbitmap(default=str(APP_DIR / "assets" / "whisper-dictation.ico"))
    except tk.TclError:
        pass

    cfg = app.config
    mode_var = tk.StringVar(value=cfg.cleanup_mode)
    engine_var = tk.StringVar(value=cfg.cleanup_engine)
    compute_var = tk.StringVar(value="GPU" if cfg.device == "cuda" else "CPU")
    hotkey_var = tk.StringVar(value=cfg.hotkey)
    whisper_model_var = tk.StringVar(value=cfg.model_size)
    openai_model_var = tk.StringVar(value=cfg.openai_model)
    ollama_model_var = tk.StringVar(value=cfg.ollama_model)
    status_var = tk.StringVar(value="Ready")

    colors = {
        "bg": "#1f1f1f",
        "panel": "#292929",
        "panel2": "#222222",
        "fg": "#f4f4f4",
        "muted": "#9a9a9a",
        "line": "#3a3a3a",
        "accent": "#ffffff",
    }

    def label(parent_frame: tk.Widget, text: str, color: str = "fg", size: int = 9, bold: bool = False) -> tk.Label:
        font = ("Segoe UI", size, "bold" if bold else "normal")
        return tk.Label(parent_frame, text=text, fg=colors[color], bg=parent_frame.cget("bg"), font=font)

    def entry(parent_frame: tk.Widget, variable: tk.StringVar, show: str = "") -> tk.Entry:
        return tk.Entry(
            parent_frame,
            textvariable=variable,
            show=show,
            bg="#151515",
            fg=colors["fg"],
            insertbackground=colors["fg"],
            relief="flat",
            font=("Segoe UI", 9),
        )

    def option(parent_frame: tk.Widget, variable: tk.StringVar, values: tuple[str, ...]) -> tk.OptionMenu:
        control = tk.OptionMenu(parent_frame, variable, *values)
        control.configure(
            bg="#151515",
            fg=colors["fg"],
            activebackground="#333333",
            activeforeground=colors["fg"],
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
            anchor="w",
        )
        control["menu"].configure(bg="#151515", fg=colors["fg"], activebackground="#333333", activeforeground=colors["fg"])
        return control

    def button(parent_frame: tk.Widget, text: str, command: Callable[[], None], primary: bool = False) -> tk.Button:
        bg = "#f1f1f1" if primary else "#333333"
        fg = "#111111" if primary else colors["fg"]
        return tk.Button(
            parent_frame,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground="#ffffff" if primary else "#444444",
            activeforeground=fg,
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=7,
            font=("Segoe UI", 9, "bold" if primary else "normal"),
            cursor="hand2",
        )

    def field(parent_frame: tk.Widget, title: str, control: tk.Widget) -> None:
        wrap = tk.Frame(parent_frame, bg=colors["panel"])
        wrap.pack(fill="x", pady=(0, 10))
        label(wrap, title, "muted", 8, True).pack(anchor="w", pady=(0, 5))
        control.pack(in_=wrap, fill="x", ipady=5)

    def open_key_file() -> None:
        ensure_env_file()
        os.startfile(ENV_PATH)
        status_var.set("Opened API key file")
        refresh_key_status()

    def refresh_key_status() -> None:
        key_status.configure(
            text="OpenAI key detected" if get_env_value("OPENAI_API_KEY") else "No OpenAI key found",
            fg="#7bd88f" if get_env_value("OPENAI_API_KEY") else "#ffcc66",
        )

    def save() -> None:
        compute = compute_var.get()
        updates = {
            "cleanup_mode": mode_var.get(),
            "cleanup_engine": engine_var.get(),
            "device": "cuda" if compute == "GPU" else "cpu",
            "compute_type": "float16" if compute == "GPU" else "int8",
            "hotkey": hotkey_var.get().strip() or cfg.hotkey,
            "model_size": whisper_model_var.get().strip() or cfg.model_size,
            "openai_model": openai_model_var.get().strip() or cfg.openai_model,
            "ollama_model": ollama_model_var.get().strip() or cfg.ollama_model,
        }
        app.apply_settings(updates)
        status_var.set("Saved")
        window.after(550, window.destroy)

    header = tk.Frame(window, bg=colors["bg"], padx=18, pady=(16, 10))
    header.pack(fill="x")
    label(header, "Whisper Dictation", size=15, bold=True).pack(anchor="w")
    label(header, "Fast dictation, cleanup, and paste settings", "muted", 9).pack(anchor="w", pady=(3, 0))

    body = tk.Frame(window, bg=colors["panel"], padx=16, pady=14)
    body.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    grid = tk.Frame(body, bg=colors["panel"])
    grid.pack(fill="x")

    left = tk.Frame(grid, bg=colors["panel"])
    left.pack(side="left", fill="x", expand=True, padx=(0, 7))
    right = tk.Frame(grid, bg=colors["panel"])
    right.pack(side="left", fill="x", expand=True, padx=(7, 0))

    field(left, "Cleanup", option(left, mode_var, ("raw", "clean", "enhanced")))
    field(right, "Engine", option(right, engine_var, ("openai", "ollama", "off")))
    field(left, "Transcription", option(left, compute_var, ("CPU", "GPU")))
    field(right, "Hotkey", entry(right, hotkey_var))

    label(body, "Models", "fg", 10, True).pack(anchor="w", pady=(4, 8))
    field(body, "OpenAI cleanup model", entry(body, openai_model_var))
    field(body, "Ollama cleanup model", entry(body, ollama_model_var))
    field(body, "Whisper model", entry(body, whisper_model_var))

    key_panel = tk.Frame(body, bg=colors["panel2"], padx=12, pady=10)
    key_panel.pack(fill="x", pady=(2, 12))
    key_row = tk.Frame(key_panel, bg=colors["panel2"])
    key_row.pack(fill="x")
    key_status = label(key_row, "", "muted", 9, True)
    key_status.pack(side="left")
    label(key_panel, "OpenAI cleanup is usually the fastest option and does not use your GPU.", "muted", 8).pack(anchor="w", pady=(5, 0))
    refresh_key_status()

    quick = tk.Frame(body, bg=colors["panel"])
    quick.pack(fill="x", pady=(0, 10))
    button(quick, "API Key", open_key_file).pack(side="left", fill="x", expand=True, padx=(0, 6))
    button(quick, "History", open_latest_history).pack(side="left", fill="x", expand=True, padx=6)
    button(quick, "Logs", lambda: (TRANSCRIPT_LOG_DIR.mkdir(exist_ok=True), os.startfile(TRANSCRIPT_LOG_DIR))).pack(side="left", fill="x", expand=True, padx=(6, 0))

    footer = tk.Frame(window, bg=colors["bg"], padx=14, pady=(0, 14))
    footer.pack(fill="x")
    label(footer, "", "muted", 8).pack(side="left")
    status_label = tk.Label(footer, textvariable=status_var, fg=colors["muted"], bg=colors["bg"], font=("Segoe UI", 8))
    status_label.pack(side="left")
    button(footer, "Cancel", window.destroy).pack(side="right", padx=(8, 0))
    button(footer, "Save", save, primary=True).pack(side="right")

    window.update_idletasks()
    x = max(0, window.winfo_screenwidth() - window.winfo_width() - 28)
    y = max(0, window.winfo_screenheight() - window.winfo_height() - 86)
    window.geometry(f"+{x}+{y}")
    window.lift()
    window.focus_force()
    return window


def open_history_window() -> None:
    TRANSCRIPT_LOG_DIR.mkdir(exist_ok=True)
    latest = sorted(TRANSCRIPT_LOG_DIR.glob("*.txt"), key=lambda path: path.stat().st_mtime, reverse=True)
    content = "No dictation history yet."
    if latest:
        content = latest[0].read_text(encoding="utf-8")

    root = tk.Tk()
    root.title("Whisper Dictation History")
    root.geometry("760x560")
    root.configure(bg="#202020")

    header = tk.Frame(root, bg="#202020", padx=16, pady=12)
    header.pack(fill="x")
    tk.Label(header, text="Dictation History", fg="#ffffff", bg="#202020", font=("Segoe UI", 14, "bold")).pack(side="left")

    body = tk.Frame(root, bg="#202020", padx=16, pady=(0, 16))
    body.pack(fill="both", expand=True)
    text = tk.Text(
        body,
        bg="#111111",
        fg="#f2f2f2",
        insertbackground="#ffffff",
        relief="flat",
        wrap="word",
        font=("Segoe UI", 10),
        padx=12,
        pady=12,
    )
    text.pack(fill="both", expand=True)
    text.insert("1.0", content)
    text.configure(state="disabled")

    root.mainloop()


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        return AppConfig()
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    fields = {field.name for field in AppConfig.__dataclass_fields__.values()}
    return AppConfig(**{key: value for key, value in data.items() if key in fields})


def ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    ENV_PATH.write_text("OPENAI_API_KEY=\n", encoding="utf-8")


def load_env_file() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in ENV_PATH.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_env_value(key: str) -> Optional[str]:
    return os.environ.get(key) or load_env_file().get(key)


def save_config(config: AppConfig) -> None:
    data = {field: getattr(config, field) for field in AppConfig.__dataclass_fields__}
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def trim_silence(audio: np.ndarray, threshold: float = 0.012, padding_ms: int = 200) -> np.ndarray:
    if audio.size == 0:
        return audio

    loud = np.abs(audio) > threshold
    if not np.any(loud):
        return audio

    first = int(np.argmax(loud))
    last = int(len(loud) - np.argmax(loud[::-1]))
    padding = int(16000 * padding_ms / 1000)
    start = max(0, first - padding)
    end = min(audio.size, last + padding)
    return audio[start:end]


def write_temp_wav(audio: np.ndarray, sample_rate: int) -> Path:
    normalized = np.clip(audio, -1.0, 1.0)
    pcm = (normalized * 32767).astype(np.int16)

    handle = tempfile.NamedTemporaryFile(prefix="whisper-dictation-", suffix=".wav", delete=False)
    path = Path(handle.name)
    handle.close()

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return path


def paste_text(text: str, target_hwnd: Optional[int], restore_clipboard: bool = True) -> None:
    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException:
            previous = None

    normalized = normalize_output_text(text)
    pyperclip.copy(normalized)
    restore_foreground_window(target_hwnd)
    time.sleep(0.25)
    send_ctrl_v()
    log_event(f"pasted {len(normalized)} chars to hwnd={target_hwnd}")

    if restore_clipboard and previous is not None:
        time.sleep(3.0)
        pyperclip.copy(previous)


def normalize_spacing(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_output_text(text: str) -> str:
    lines = [normalize_spacing(line) for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    compact_lines: list[str] = []
    previous_blank = False
    for line in lines:
        if line:
            compact_lines.append(line)
            previous_blank = False
        elif compact_lines and not previous_blank:
            compact_lines.append("")
            previous_blank = True
    return "\n".join(compact_lines).strip()


def main() -> None:
    instance: Optional[SingleInstance] = None
    try:
        instance = SingleInstance(LOCK_PATH)
        app = DictationApp(load_config())
        app.run()
    except RuntimeError as exc:
        print(exc)
    except KeyboardInterrupt:
        pass
    finally:
        if instance is not None:
            instance.release()


if __name__ == "__main__":
    main()
