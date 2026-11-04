"""Orchestrate source fetchers and return a canonical API response.

Sync-level fallback hierarchy (when pass_param=False):

  syllabus=true   → apple_music(syllable) → lrcmux+apple_music(word) → all sources(line)
  word=true       → lrcmux+apple_music(word) → all sources(line)
  timestamps=true → all sources (line-level)
  timestamps=false → all sources except apple_music (plain only)

Apple Music is the only source that does NOT provide plain (unsynced) lyrics,
so it is excluded when timestamps=False.

When pass_param=true (explicit &pass=true), the user's sequence is used as-is
with a single phase — no sync-level fallback.
"""

from __future__ import annotations

import asyncio
import inspect
import time

from src.core import providers
from src.core.tiers import detect_tier
from src.core.verifier import verdict_summary, verify_result
from src.logger import get_logger
from src.sources import ALL_FETCHERS

logger = get_logger("fetch_controller")

_SOURCE_ORDER = ["lrclib", "lrcmux", "genius", "youtube", "netease", "megalobiz", "musixmatch", "apple_music"]
_SOURCE_BY_ID = {
	1: "genius",
	2: "lrclib",
	3: "youtube",
	4: "netease",
	5: "megalobiz",
	6: "musixmatch",
	7: "lrcmux",
	8: "apple_music",
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


def _meta_init(meta: dict | None) -> dict:
	if meta is None:
		meta = {}
	meta.setdefault("accepted", [])
	meta.setdefault("rejected", [])
	meta.setdefault("errors", [])
	meta.setdefault("not_found", [])
	meta.setdefault("skipped", [])
	meta.setdefault("attempts", 0)
	return meta


async def _try_fetcher(
	source_name: str,
	artist: str,
	song: str,
	timestamps: bool,
	word_level: bool = False,
	syllabus: bool = False,
	meta: dict | None = None,
):
	fetcher = ALL_FETCHERS.get(source_name)
	if not fetcher:
		return None

	# Single choke point: quota, breaker, and bulkhead before any network I/O.
	allowed, reason = providers.try_acquire(source_name)
	if not allowed:
		if meta is not None:
			meta["skipped"].append({"provider": source_name, "reason": reason})
		logger.info("Skipping %s for %r - %r: %s", source_name, artist, song, reason)
		return None

	if meta is not None:
		meta["attempts"] += 1

	started = time.perf_counter()
	try:
		async with providers.slot(source_name):
			if source_name in ("lrcmux", "apple_music"):
				outcome = fetcher.fetch(artist, song, timestamps=timestamps, word_level=word_level, syllabus=syllabus)
			else:
				outcome = fetcher.fetch(artist, song, timestamps=timestamps)
			result = await outcome if inspect.isawaitable(outcome) else outcome
	except asyncio.CancelledError:
		# Fast-mode fan-out cancels the losing tasks. Do not let that leave a
		# half-open breaker probe permanently in flight.
		providers.record_aborted(source_name)
		raise
	except Exception as e:
		# One provider must never take down the fallback chain, but failures
		# have to be visible: debug-level swallowing hid permanent breakage.
		error = providers.redact(f"{type(e).__name__}: {e}")
		providers.record_failure(source_name, error)
		logger.warning("Provider %s failed for %r - %r: %s", source_name, artist, song, error)
		if meta is not None:
			meta["errors"].append({"provider": source_name, "error": error})
		return None

	latency = time.perf_counter() - started

	if result is None:
		# A clean "no such song" response is not a transport failure.
		providers.record_success(source_name, latency, not_found=True)
		if meta is not None:
			meta["not_found"].append(source_name)
		return None

	verdict = verify_result(artist, song, result)
	if not verdict.get("accepted"):
		providers.record_rejected(source_name, str(verdict.get("reason", "invalid")))
		logger.warning(
			"Provider %s returned a wrong-song result for %r - %r (confidence %.2f): %s",
			source_name,
			artist,
			song,
			verdict.get("confidence", 0.0),
			verdict.get("reason", ""),
		)
		if meta is not None:
			meta["rejected"].append({
				"provider": source_name,
				**verdict_summary(verdict),
			})
		return None

	providers.record_success(source_name, latency)
	if meta is not None:
		meta["accepted"].append({
			"provider": source_name,
			"confidence": verdict.get("confidence", 0.0),
			"latency_ms": round(latency * 1000, 1),
		})
	return result


def _is_timestamped_result(result: dict | None) -> bool:
	if not result:
		return False
	return bool(result.get("hasTimestamps") or result.get("timed_lyrics"))


def _is_word_synced_result(result: dict | None) -> bool:
	if not result:
		return False
	if result.get("sync_level") == "word":
		return True
	timed = result.get("timed_lyrics") or []
	return any(isinstance(line, dict) and "words" in line for line in timed)


def _is_syllable_synced_result(result: dict | None) -> bool:
	if not result:
		return False
	if result.get("sync_level") == "syllable":
		return True
	timed = result.get("timed_lyrics") or []
	return any(
		isinstance(line, dict)
		and "words" in line
		and any("syllables" in w for w in line.get("words", []))
		for line in timed
	)


# ── Phase-based sync-level fallback ────────────────────────────────────────────

def _accept_check(word_level: bool, syllabus: bool, timestamps: bool):
	"""Return a predicate that checks whether a result matches the requested sync level."""
	if syllabus:
		return _is_syllable_synced_result
	if word_level:
		return _is_word_synced_result
	if timestamps:
		return _is_timestamped_result
	return lambda r: r is not None


def _build_sync_phases(
	source_names: list[str],
	word_level: bool,
	syllabus: bool,
	timestamps: bool,
) -> list[dict]:
	"""Build ordered phase list for the sync-level fallback hierarchy.

	Each phase is a dict with:
	    sources    — list of source names to try
	    word_level — whether to request word-level timing
	    syllabus   — whether to request syllable-level timing
	    accept     — function(result) -> bool, checks if the result matches this phase
	"""
	phases: list[dict] = []

	if syllabus and timestamps:
		# Phase 1: syllable-level from Apple Music only
		if "apple_music" in source_names:
			phases.append({
				"sources": ["apple_music"],
				"word_level": True,
				"syllabus": True,
				"accept": _is_syllable_synced_result,
			})
		# Phase 2: word-level from lrcmux + apple_music
		word_srcs = [s for s in ["lrcmux", "apple_music"] if s in source_names]
		if word_srcs:
			phases.append({
				"sources": word_srcs,
				"word_level": True,
				"syllabus": False,
				"accept": _is_word_synced_result,
			})
	# Fall through to line-level phase below

	if word_level and timestamps:
		# Phase 1: word-level from lrcmux + apple_music
		word_srcs = [s for s in ["lrcmux", "apple_music"] if s in source_names]
		if word_srcs:
			phases.append({
				"sources": word_srcs,
				"word_level": True,
				"syllabus": False,
				"accept": _is_word_synced_result,
			})

	# Final phase: line-level (or plain) from all sources. When a word/syllable
	# request has already been narrowed to word-capable providers, the earlier
	# phase queried exactly the same sources and captured their best fallback.
	# Repeating it would double latency for no new result.
	word_only = bool(source_names) and set(source_names) <= {"lrcmux", "apple_music"}
	if not (word_only and (word_level or syllabus)):
		phases.append({
			"sources": source_names,
			"word_level": False,
			"syllabus": False,
			"accept": _is_timestamped_result if timestamps else (lambda r: r is not None),
		})

	return phases


async def _try_phase(
	phase: dict,
	artist: str,
	song: str,
	timestamps: bool,
	fast_mode: bool,
	fast_timeout: int,
	meta: dict | None = None,
) -> dict | None:
	"""Try sources within a phase. Returns first matching result or best fallback."""
	sources = phase["sources"]
	wl = phase["word_level"]
	syl = phase["syllabus"]
	accept = phase["accept"]

	if not sources:
		return None

	if fast_mode and len(sources) > 1:
		# Only fan out to providers that can actually serve right now. This
		# keeps fast mode from burning quota on open breakers or empty buckets.
		eligible = [name for name in sources if name in ALL_FETCHERS and providers.available(name)]
		if not eligible:
			if meta is not None:
				meta["skipped"].append({"provider": ",".join(sources), "reason": "no_eligible_provider"})
			return None

		loop = asyncio.get_running_loop()
		deadline = loop.time() + fast_timeout
		tasks = [
			asyncio.create_task(_try_fetcher(name, artist, song, timestamps, wl, syl, meta))
			for name in eligible
		]
		best_fallback = None
		pending = set(tasks)
		try:
			while pending:
				remaining = max(0.0, deadline - loop.time())
				if remaining <= 0:
					break
				done, pending = await asyncio.wait(
					pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
				)
				if not done:
					break
				for task in done:
					try:
						result = task.result()
					except asyncio.CancelledError:
						continue
					except Exception:
						continue
					if result and accept(result):
						return result
					if result and best_fallback is None:
						best_fallback = result
			return best_fallback
		finally:
			for task in tasks:
				if not task.done():
					task.cancel()

	# Sequential
	best_fallback = None
	for source_name in sources:
		result = await _try_fetcher(source_name, artist, song, timestamps, wl, syl, meta)
		if result and accept(result):
			return result
		elif result and best_fallback is None:
			best_fallback = result

	return best_fallback


async def fetch_lyrics_controller(
	artist: str,
	song: str,
	timestamps: bool = False,
	pass_param: bool = False,
	sequence=None,
	fast_mode: bool = False,
	fast_timeout: int = 20,
	word_level: bool = False,
	syllabus: bool = False,
	meta: dict | None = None,
) -> dict:
	meta = _meta_init(meta)
	try:
		fast_timeout = max(1, min(int(fast_timeout or 20), 60))
	except (TypeError, ValueError):
		fast_timeout = 20

	source_names = _normalize_sequence(sequence)
	if not pass_param and sequence is None:
		source_names = [name for name in _SOURCE_ORDER if name in ALL_FETCHERS]

	# Apple Music does not provide plain lyrics — exclude when timestamps=False
	if not timestamps:
		source_names = [s for s in source_names if s != "apple_music"]

	# Word/syllable sync is only available from lrcmux and Apple Music. For
	# normal requests, restrict the whole fallback chain to those providers so
	# we never burn quota on a provider that cannot satisfy the request.
	# Explicit &pass=true sequences are left untouched (the caller opted in).
	if timestamps and (word_level or syllabus) and not pass_param:
		word_capable = [s for s in ("lrcmux", "apple_music") if s in ALL_FETCHERS]
		if word_capable:
			source_names = word_capable

	# ── Build phase list ────────────────────────────────────────────────────
	if pass_param:
		# User explicitly requested specific sources — single phase, no fallback
		phases = [{
			"sources": source_names,
			"word_level": word_level,
			"syllabus": syllabus,
			"accept": _accept_check(word_level, syllabus, timestamps),
		}]
	else:
		# Phase-based sync-level fallback
		phases = _build_sync_phases(source_names, word_level, syllabus, timestamps)

	# ── Try phases in order ─────────────────────────────────────────────────
	overall_fallback = None
	for phase in phases:
		result = await _try_phase(
			phase, artist, song, timestamps, fast_mode, fast_timeout, meta
		)
		if result and phase["accept"](result):
			meta["tier"] = detect_tier(result)
			meta["outcome"] = "success"
			return {"status": "success", "data": result}
		if result and overall_fallback is None:
			overall_fallback = result

	if overall_fallback:
		meta["tier"] = detect_tier(overall_fallback)
		meta["outcome"] = "success"
		return {"status": "success", "data": overall_fallback}

	# Distinguish "nobody has this song" from "every provider broke" or "the
	# only answer was a wrong song". Only a clean absence may be negative-cached.
	if meta["skipped"]:
		meta["outcome"] = "incomplete"
	elif meta["errors"]:
		meta["outcome"] = "error"
	elif meta["rejected"] or not meta["not_found"]:
		meta["outcome"] = "rejected" if meta["rejected"] else "error"
	else:
		meta["outcome"] = "not_found"
	return {
		"status": "error",
		"error": {
			"message": "No lyrics found",
			"details": "All enabled fetchers returned no result",
		},
	}
