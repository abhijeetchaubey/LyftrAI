"""
API Key Manager module for managing LLM provider keys and failover pools.
"""
from typing import List, Tuple, Optional


class KeyEntry:
    """Represents a managed API key with an assigned identifier."""
    def __init__(self, key_id: str, secret: str):
        self.key_id = key_id
        self._secret = secret

    @property
    def secret(self) -> str:
        return self._secret

    def __repr__(self) -> str:
        masked = f"{self._secret[:4]}...{self._secret[-4:]}" if len(self._secret) > 8 else "***"
        return f"<KeyEntry {self.key_id}: {masked}>"


class KeyManager:
    """
    Manages a pool of API keys, assigning identifiers key_1, key_2, etc.,
    and providing sequential access for failover.
    """
    def __init__(self, raw_keys: Optional[List[str]] = None):
        self.keys: List[KeyEntry] = []
        if raw_keys:
            self.load_keys(raw_keys)

    def load_keys(self, raw_keys: List[str]) -> None:
        """Load and assign sequential identifiers (key_1, key_2, ...) to keys."""
        self.keys = []
        for index, key in enumerate(raw_keys, start=1):
            cleaned = key.strip()
            if cleaned:
                self.keys.append(KeyEntry(key_id=f"key_{index}", secret=cleaned))

    @property
    def count(self) -> int:
        """Return the number of configured keys."""
        return len(self.keys)

    def has_minimum_keys(self, min_keys: int = 2) -> bool:
        """Check if at least min_keys are configured."""
        return len(self.keys) >= min_keys

    def get_entries(self) -> List[KeyEntry]:
        """Return all managed key entries in order."""
        return list(self.keys)

    def get_key_by_id(self, key_id: str) -> Optional[KeyEntry]:
        """Find a key entry by its identifier."""
        for entry in self.keys:
            if entry.key_id == key_id:
                return entry
        return None

    # def __repr__(self) -> str:
    #     return f"<KeyManager total_keys={len(self.keys)} ids={[k.key_id for k in self.keys]}>"
    def __repr__(self) -> str:
        return f"<KeyEntry {self.key_id}: configured>"