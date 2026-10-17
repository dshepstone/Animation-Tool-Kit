"""Versioned, portable simulation settings. No Maya dependencies."""
from dataclasses import dataclass, asdict
import json
import math
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    mode: str = "rotation"
    frequency: float = 2.0
    damping: float = 0.45
    strength: float = 1.0
    substeps: int = 8
    preroll: int = 12
    axis: str = "+X"
    length: float = 5.0
    channels: str = "XYZ"
    tip_mode: str = "chain"
    optimize_bake: bool = False
    key_tolerance: float = 0.25

    def __post_init__(self):
        if self.mode not in ("rotation", "translation"):
            raise ValueError("Mode must be rotation or translation")
        if self.axis not in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
            raise ValueError("Invalid endpoint axis")
        if (not isinstance(self.channels, str) or not self.channels or
                any(a not in "XYZ" for a in self.channels) or
                len(set(self.channels)) != len(self.channels)):
            raise ValueError("Choose at least one output channel: X, Y, Z")
        object.__setattr__(self, "channels", "".join(a for a in "XYZ" if a in self.channels))
        if self.tip_mode not in ("chain", "axis"):
            raise ValueError("Tip mode must be chain or axis")
        if type(self.optimize_bake) is not bool:
            raise ValueError("Optimize bake must be a boolean")
        for name, low, high in (("frequency", .05, 30), ("damping", 0, 3),
                                ("strength", 0, 1), ("length", .001, 100000),
                                ("key_tolerance", 0, 100000)):
            value = getattr(self, name)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError("{} must be between {} and {}".format(name, low, high))
        for name, low, high in (("substeps", 1, 128), ("preroll", 0, 1000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError("{} must be an integer between {} and {}".format(name, low, high))

    def save(self, path):
        Path(path).write_text(json.dumps({"schema": 1, "settings": asdict(self)}, indent=2),
                              encoding="utf-8")

    def simulation_key(self):
        """Bake-only options can change after preview without invalidating solve."""
        return {k: v for k, v in asdict(self).items()
                if k not in ("optimize_bake", "key_tolerance")}

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema") != 1:
            raise ValueError("Unsupported preset version")
        # Older presets explicitly described a manual axis/length endpoint.
        data["settings"].setdefault("tip_mode", "axis")
        return cls(**data["settings"])
