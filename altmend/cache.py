"""Remember what the model said about each picture, so a second run is free.

The key is the image itself plus the settings that change the answer, which
means moving or renaming a file does not waste a model call.
"""

import hashlib
import json
from pathlib import Path

CACHE_FILENAME = ".altmend-cache.json"


class DescriptionCache:
    def __init__(self, folder: Path, enabled: bool = True):
        self.path = folder / CACHE_FILENAME
        self.enabled = enabled
        self.entries: dict[str, str] = {}
        self.hits = 0
        if self.enabled and self.path.is_file():
            try:
                self.entries = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.entries = {}

    @staticmethod
    def key_for(image_bytes: bytes, *settings: str) -> str:
        digest = hashlib.sha256(image_bytes)
        for setting in settings:
            digest.update(b"\x00")
            digest.update(str(setting).encode("utf-8"))
        return digest.hexdigest()[:32]

    def get(self, key: str) -> str | None:
        if not self.enabled:
            return None
        remembered = self.entries.get(key)
        if remembered is not None:
            self.hits += 1
        return remembered

    def put(self, key: str, description: str) -> None:
        if self.enabled:
            self.entries[key] = description

    def save(self) -> None:
        if not self.enabled or not self.entries:
            return
        try:
            self.path.write_text(json.dumps(self.entries, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass  # a cache that cannot be written is not worth stopping the run for
