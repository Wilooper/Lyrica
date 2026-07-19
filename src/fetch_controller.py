"""Orchestrate source fetchers and return a canonical API response."""

from __future__ import annotations

import asyncio

from src.sources import ALL_FETCHERS


_SOURCE_ORDER = ["genius", "lrclib", "youtube", "netease", "megalobiz", "musixmatch", "simpmusic"]
_SOURCE_BY_ID = {
	1: "genius",
	2: "lrclib",
	3: "youtube",
	4: "netease",
	5: "megalobiz",
	6: "musixmatch",
	7: "simpmusic",
}


def _normalize_sequence(sequence) -> list[str]:
	if sequence is None:
		return [name for name in _SOURCE_ORDER if name in ALL_FETCHERS]

	if isinstance(sequence, str):
		parts = [part.strip() for part in sequence.split(",")]
	else:
		parts = list(sequence)

	normalized: list[str] = []
	for part in parts:
		if part in (None, ""):
			continue
		try:
			source_name = _SOURCE_BY_ID[int(part)]
		except (ValueError, KeyError, TypeError):
			source_name = str(part).strip().lower()
		if source_name in ALL_FETCHERS and source_name not in normalized:
			normalized.append(source_name)

	if not normalized:
		return [name for name in _SOURCE_ORDER if name in ALL_FETCHERS]
	return normalized


async def _try_fetcher(source_name: str, artist: str, song: str, timestamps: bool):
	fetcher = ALL_FETCHERS.get(source_name)
	if not fetcher:
		return None

	try:
		if source_name == "lrclib":
			return await fetcher.fetch(artist, song, timestamps=timestamps)
		return await fetcher.fetch(artist, song, timestamps=timestamps)
	except Exception:
		return None


def _is_timestamped_result(result: dict | None) -> bool:
	if not result:
		return False
	return bool(result.get("hasTimestamps") or result.get("timed_lyrics"))


async def fetch_lyrics_controller(
	artist: str,
	song: str,
	timestamps: bool = False,
	pass_param: bool = False,
	sequence=None,
	fast_mode: bool = False,
	fast_timeout: int = 20,
) -> dict:
	source_names = _normalize_sequence(sequence)
	if not pass_param and sequence is None:
		source_names = [name for name in _SOURCE_ORDER if name in ALL_FETCHERS]

	if fast_mode and len(source_names) > 1:
		tasks = [asyncio.create_task(_try_fetcher(name, artist, song, timestamps)) for name in source_names]
		try:
			done, pending = await asyncio.wait(tasks, timeout=fast_timeout, return_when=asyncio.FIRST_COMPLETED)
			for task in done:
				result = task.result()
				if result and (not timestamps or _is_timestamped_result(result)):
					for pending_task in pending:
						pending_task.cancel()
					return {"status": "success", "data": result}

			for task in pending:
				try:
					result = await task
					if result and (not timestamps or _is_timestamped_result(result)):
						for pending_task in pending:
							if pending_task is not task:
								pending_task.cancel()
						return {"status": "success", "data": result}
				except asyncio.CancelledError:
					continue
		finally:
			for task in tasks:
				if not task.done():
					task.cancel()

	for source_name in source_names:
		result = await _try_fetcher(source_name, artist, song, timestamps)
		if result and (not timestamps or _is_timestamped_result(result)):
			return {"status": "success", "data": result}

	return {
		"status": "error",
		"error": {
			"message": "No lyrics found",
			"details": "All enabled fetchers returned no result",
		},
	}
