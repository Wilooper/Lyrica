"""User configuration loader for optional .lyrica.config files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import configparser
import os
from threading import RLock


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
	if value is None:
		return default
	if isinstance(value, bool):
		return value
	return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
	if value is None or not value.strip():
		return default
	try:
		return int(value.strip())
	except ValueError:
		return default


def _parse_sequence(value: str | None) -> list[int]:
	if not value:
		return [1, 2, 3, 4, 5, 6, 7]
	items: list[int] = []
	for part in value.split(","):
		part = part.strip()
		if not part:
			continue
		try:
			items.append(int(part))
		except ValueError:
			continue
	return items or [1, 2, 3, 4, 5, 6, 7]


@dataclass
class UserConfig:
	config_path: str | None = None
	default_timestamps: bool = False
	default_mood: bool = False
	default_metadata: bool = False
	default_fast: bool = False
	default_sequence: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5, 6, 7])
	reload_on_config_change: bool = False
	genius_rpm: int = 5
	lrclib_rpm: int = 30
	youtube_rpm: int = 10
	netease_rpm: int = 20
	megalobiz_rpm: int = 15
	musixmatch_rpm: int = 15
	simpmusic_rpm: int = 20
	fast_timeout: int = 20
	request_timeout: int = 60
	cache_ttl: int | None = None
	cache_dir: str | None = None
	proxies: list[str] = field(default_factory=list)

	def to_dict(self) -> dict:
		return {
			"config_path": self.config_path,
			"defaults": {
				"timestamps": self.default_timestamps,
				"mood": self.default_mood,
				"metadata": self.default_metadata,
				"fast": self.default_fast,
				"sequence": self.default_sequence,
			},
			"reload": {"reload_on_config_change": self.reload_on_config_change},
			"rate_limits": {
				"genius_rpm": self.genius_rpm,
				"lrclib_rpm": self.lrclib_rpm,
				"youtube_rpm": self.youtube_rpm,
				"netease_rpm": self.netease_rpm,
				"megalobiz_rpm": self.megalobiz_rpm,
				"musixmatch_rpm": self.musixmatch_rpm,
				"simpmusic_rpm": self.simpmusic_rpm,
			},
			"proxies": {"items": self.proxies, "persist": False},
			"cache": {"ttl": self.cache_ttl, "dir": self.cache_dir},
			"server": {"fast_timeout": self.fast_timeout, "request_timeout": self.request_timeout},
		}


_LOCK = RLock()
_USER_CONFIG = UserConfig()


def _candidate_paths() -> list[Path]:
	paths: list[Path] = []
	env_path = os.getenv("LYRICA_CONFIG")
	if env_path:
		paths.append(Path(env_path).expanduser())
	paths.append(Path.cwd() / ".lyrica.config")
	paths.append(Path.home() / ".lyrica.config")
	return paths


def _load_from_path(path: Path) -> UserConfig:
	cfg = UserConfig(config_path=str(path))
	parser = configparser.ConfigParser(interpolation=None)
	parser.read(path, encoding="utf-8")

	if parser.has_section("defaults"):
		defaults = parser["defaults"]
		cfg.default_timestamps = _parse_bool(defaults.get("timestamps"), cfg.default_timestamps)
		cfg.default_mood = _parse_bool(defaults.get("mood"), cfg.default_mood)
		cfg.default_metadata = _parse_bool(defaults.get("metadata"), cfg.default_metadata)
		cfg.default_fast = _parse_bool(defaults.get("fast"), cfg.default_fast)
		cfg.default_sequence = _parse_sequence(defaults.get("sequence"))

	if parser.has_section("reload"):
		cfg.reload_on_config_change = _parse_bool(parser["reload"].get("reload_on_config_change"), False)

	if parser.has_section("rate_limits"):
		rate_limits = parser["rate_limits"]
		cfg.genius_rpm = _parse_int(rate_limits.get("genius_rpm"), cfg.genius_rpm)
		cfg.lrclib_rpm = _parse_int(rate_limits.get("lrclib_rpm"), cfg.lrclib_rpm)
		cfg.youtube_rpm = _parse_int(rate_limits.get("youtube_rpm"), cfg.youtube_rpm)
		cfg.netease_rpm = _parse_int(rate_limits.get("netease_rpm"), cfg.netease_rpm)
		cfg.megalobiz_rpm = _parse_int(rate_limits.get("megalobiz_rpm"), cfg.megalobiz_rpm)
		cfg.musixmatch_rpm = _parse_int(rate_limits.get("musixmatch_rpm"), cfg.musixmatch_rpm)
		cfg.simpmusic_rpm = _parse_int(rate_limits.get("simpmusic_rpm"), cfg.simpmusic_rpm)

	if parser.has_section("cache"):
		cache = parser["cache"]
		ttl = cache.get("ttl")
		cfg.cache_ttl = _parse_int(ttl, 86400) if ttl is not None else None
		cfg.cache_dir = cache.get("dir") or None

	if parser.has_section("server"):
		server = parser["server"]
		cfg.fast_timeout = _parse_int(server.get("fast_timeout"), cfg.fast_timeout)
		cfg.request_timeout = _parse_int(server.get("request_timeout"), cfg.request_timeout)

	if parser.has_section("proxies"):
		cfg.proxies = [value for key, value in parser["proxies"].items() if key.startswith("proxy_") and value.strip()]

	return cfg


def load_user_config() -> UserConfig:
	with _LOCK:
		global _USER_CONFIG
		for path in _candidate_paths():
			if path.is_file():
				_USER_CONFIG = _load_from_path(path)
				return _USER_CONFIG
		_USER_CONFIG = UserConfig()
		return _USER_CONFIG


def get_user_config() -> UserConfig:
	with _LOCK:
		return _USER_CONFIG


def reload_user_config() -> UserConfig:
	return load_user_config()
