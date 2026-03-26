"""
Anagram Quest — Game Master Server (Phase 4b)

FastAPI backend with:
  - GameEngine: 5-level game state machine
  - BankingEngine: MDP-based Expected Value optimizer
  - OracleClient: Async HTTP calls to HF Spaces LLM
  - SSE streaming: Real-time "AI Thinking" events for the frontend
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ══════════════════════════════════════════════════════════════
# Oracle Client — Async calls to HF Spaces LLM
# ══════════════════════════════════════════════════════════════
ORACLE_URL = "https://ailanidivyansh-anagram-quest-oracle.hf.space"
MATCH_TTL_IDLE_SECONDS = 20 * 60
MATCH_TTL_PLAYING_SECONDS = 45 * 60
GC_INTERVAL_SECONDS = 60
ORACLE_CACHE_TTL_SECONDS = 15 * 60
ORACLE_CACHE_MAX_ENTRIES = 1024

_oracle_client: httpx.AsyncClient | None = None
_oracle_cache: dict[str, tuple[float, list[str]]] = {}
_oracle_key_locks: dict[str, asyncio.Lock] = {}
_oracle_lock_registry_lock = asyncio.Lock()


def _oracle_cache_key(letters: list[str]) -> str:
    return "".join(sorted(letter.upper() for letter in letters))


def _trim_oracle_cache() -> None:
    if len(_oracle_cache) <= ORACLE_CACHE_MAX_ENTRIES:
        return
    oldest_key = min(_oracle_cache.items(), key=lambda item: item[1][0])[0]
    del _oracle_cache[oldest_key]


async def _get_oracle_key_lock(key: str) -> asyncio.Lock:
    async with _oracle_lock_registry_lock:
        lock = _oracle_key_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _oracle_key_locks[key] = lock
        return lock


async def _get_oracle_client() -> httpx.AsyncClient:
    global _oracle_client
    if _oracle_client is None:
        _oracle_client = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=3.0),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        )
    return _oracle_client


async def _close_oracle_client() -> None:
    global _oracle_client
    if _oracle_client is not None:
        await _oracle_client.aclose()
        _oracle_client = None


async def call_oracle(letters: list[str]) -> list[str]:
    """Call the HF Spaces Oracle to solve an anagram with cache + connection pooling."""
    key = _oracle_cache_key(letters)
    now = time.time()
    cached = _oracle_cache.get(key)
    if cached and now - cached[0] <= ORACLE_CACHE_TTL_SECONDS:
        return list(cached[1])

    key_lock = await _get_oracle_key_lock(key)
    async with key_lock:
        now = time.time()
        cached = _oracle_cache.get(key)
        if cached and now - cached[0] <= ORACLE_CACHE_TTL_SECONDS:
            return list(cached[1])

        client = await _get_oracle_client()
        resp = await client.post(
            f"{ORACLE_URL}/solve",
            json={"letters": letters},
        )
        resp.raise_for_status()
        words = [
            str(word).upper().strip()
            for word in resp.json().get("words", [])
            if str(word).strip()
        ]
        _oracle_cache[key] = (time.time(), words)
        _trim_oracle_cache()
        return list(words)


# ══════════════════════════════════════════════════════════════
# Anagram Data — 157 unified groups
# ══════════════════════════════════════════════════════════════
ANAGRAM_GROUPS = {
    # Level 1: 3-letter
    "ABT": ["BAT", "TAB"], "ACT": ["ACT", "CAT"], "ADM": ["DAM", "MAD"],
    "AEL": ["ALE", "LEA"], "AET": ["ATE", "EAT", "ETA", "TEA"],
    "AGR": ["GAR", "RAG"], "AHM": ["HAM", "MAH"], "AJR": ["JAR", "RAJ"],
    "AMP": ["AMP", "MAP"], "ANP": ["NAP", "PAN"], "ANT": ["ANT", "TAN"],
    "APS": ["ASP", "SAP", "SPA"], "APT": ["APT", "PAT", "TAP"],
    "ARS": ["ARS", "SAR"], "ART": ["ART", "RAT", "TAR"],
    "ASW": ["SAW", "WAS"], "DEN": ["DEN", "END"], "DGO": ["DOG", "GOD"],
    "ENT": ["NET", "TEN"], "GIN": ["GIN", "ING"], "GNO": ["GON", "NOG"],
    "GNU": ["GNU", "GUN", "NUG"], "HOW": ["HOW", "WHO"],
    "INP": ["NIP", "PIN"], "IPS": ["PSI", "SIP"], "LOW": ["LOW", "OWL"],
    "NOS": ["NOS", "SON"], "NOW": ["NOW", "OWN", "WON"],
    "OPT": ["OPT", "POT", "TOP"], "ORT": ["ROT", "TOR"],
    "OTW": ["OWT", "TOW", "TWO", "WOT"],
    # Level 2: 4-letter
    "ACRS": ["ARCS", "CARS", "SCAR"], "ACST": ["ACTS", "CAST", "CATS", "SCAT"],
    "ADEM": ["DAME", "MADE", "MEAD"], "ADER": ["DARE", "DEAR", "READ"],
    "AEGM": ["GAME", "MAGE"], "AHRS": ["RASH", "SHAR"],
    "AILR": ["LAIR", "LIAR", "RAIL", "RIAL"], "AILS": ["AILS", "SAIL"],
    "AIMS": ["AIMS", "AMIS"], "AIPS": ["PAIS", "PIAS"],
    "AELM": ["LAME", "MALE", "MEAL"],
    "AELP": ["LEAP", "PALE", "PEAL", "PLEA"], "AELR": ["EARL", "REAL"],
    "AELS": ["ALES", "LEAS", "SALE", "SEAL"],
    "AELT": ["LATE", "TALE", "TEAL"],
    "AEMN": ["AMEN", "MANE", "MEAN", "NAME"],
    "AENR": ["EARN", "NEAR", "RANE"], "AEPS": ["APES", "PEAS"],
    "AEPT": ["PATE", "PEAT", "TAPE"],
    "AERS": ["ARES", "EARS", "ERAS", "SEAR"],
    "AERT": ["RATE", "TARE", "TEAR"], "AERW": ["WARE", "WEAR"],
    "AEST": ["ETAS", "SATE", "SEAT", "TEAS"],
    "ALPS": ["ALPS", "LAPS", "PALS", "SLAP"],
    "ALMS": ["ALMS", "LAMS", "SLAM"], "AMOR": ["MORA", "ROAM"],
    "AMST": ["MAST", "MATS", "TAMS"],
    "ANPS": ["NAPS", "PANS", "SNAP", "SPAN"],
    "ARST": ["ARTS", "RATS", "STAR", "TARS"],
    "ADEL": ["DALE", "DEAL", "LEAD"],
    "DEIS": ["DIES", "IDES", "SIDE"], "DEOS": ["DOES", "DOSE", "ODES"],
    "EIKL": ["KEIL", "LIKE"], "EILS": ["ISLE", "LIES"],
    "EILV": ["EVIL", "LIVE", "VEIL", "VILE"],
    "EIST": ["SITE", "TIES"], "ELST": ["LEST", "LETS"],
    "ENOT": ["NOTE", "TONE"], "EORS": ["ORES", "ROSE", "SORE"],
    "GINS": ["GINS", "SIGN", "SING"], "ILNO": ["LION", "LOIN"],
    "OPST": ["OPTS", "POST", "POTS", "SPOT", "STOP", "TOPS"],
    "ORST": ["ROTS", "SORT", "TORS"],
    # Level 3: 5-letter
    "ABENR": ["BANE", "BARN", "BEAR"],
    "ADELS": ["DALES", "DEALS", "LEADS"], "ADEMS": ["DAMES", "MEADS"],
    "AEGRS": ["GEARS", "RAGES", "SAGER"], "AELNS": ["LANES", "LEANS"],
    "AELNP": ["PANEL", "PENAL", "PLANE"],
    "AELPS": ["LEAPS", "PALES", "PEALS", "PLEAS", "SEPAL"],
    "AELRT": ["ALERT", "ALTER", "LATER"],
    "AELST": ["LEAST", "SLATE", "STALE", "STEAL", "TALES", "TESLA"],
    "AEMRS": ["MARES", "MASER", "REAMS", "SMEAR"],
    "AENRS": ["EARNS", "NEARS", "SANER", "SNARE"],
    "AENST": ["ANTES", "ETNAS", "NATES", "NEATS", "STANE"],
    "AEPRS": ["PEARS", "PARSE", "REAPS", "SPARE", "SPEAR"],
    "AILNS": ["NAILS", "SLAIN", "SNAIL"],
    "AILRT": ["TRAIL", "TRIAL"], "AINRT": ["INTRA", "TRAIN"],
    "DEIRS": ["DRIES", "RIDES", "SIRED"],
    "DEIST": ["DIETS", "EDITS", "SITED", "TIDES"],
    "EERST": ["RESET", "STEER", "TREES"], "EGNOR": ["GENRO", "GONER"],
    "EILNS": ["LIENS", "LINES"],
    "EILPS": ["PILES", "PLIES", "SPIEL"],
    "EINPS": ["PINES", "SNIPE", "SPINE"],
    "EINRS": ["REINS", "RINSE", "RISEN", "SIREN"],
    "EINRT": ["INERT", "INTER", "NITER", "TRINE"],
    "EINST": ["INSET", "STEIN", "TINES"],
    "EORST": ["ROTES", "STORE", "TORES"],
    "EPRSU": ["PURSE", "SPRUE", "SUPER"], "ERSTW": ["STREW", "WREST"],
    "AELPRS": ["PARLES", "PEARLS"], "ACLRS": ["CARLS", "CLARS"],
    # Level 4: 6-letter
    "ACEIRST": ["CRISTAE", "RACIEST", "STEARIC"],
    "ACENRS": ["CANERS", "CRANES", "NACRES"],
    "ACERST": ["CASTER", "CATERS", "RECAST", "TRACES"],
    "ADEIRS": ["DARIES", "RAISED"], "ADEINR": ["DENARI", "RAINED"],
    "AEGINR": ["EARING", "GAINER", "REGAIN"],
    "AEGLNS": ["ANGLES", "GLEANS"],
    "AEGNRS": ["ANGERS", "RANGES", "SANGER"],
    "AEGNRT": ["ARGENT", "GARNET"], "AEIMNR": ["MARINE", "REMAIN"],
    "AEILNR": ["LINEAR", "NAILER"], "AEILNS": ["SALINE", "SILANE"],
    "AEINRS": ["ARISEN", "SARNIE"], "AEINST": ["INSEAT", "TISANE"],
    "AELRSV": ["LAVERS", "SALVER", "VELARS"],
    "AELRST": ["ALERTS", "ALTERS", "SLATER", "STELAR"],
    "AEMNST": ["AMENTS", "MANTES", "STAMEN"],
    "AEORST": ["OATERS", "ORATES"],
    "AEPRST": ["PASTER", "REPAST", "TAPERS", "TRAPES"],
    "AGINST": ["GIANTS", "SATING"],
    "DEGINS": ["DESIGN", "SIGNED", "SINGED"],
    "DEINRS": ["DINERS", "RINSED"],
    "DEORST": ["DOTERS", "SORTED", "STORED"],
    "DEISTU": ["DUTIES", "SUITED"], "EILNPS": ["PENSIL", "SPLINE"],
    "EILNST": ["ENLIST", "LISTEN", "SILENT", "TINSEL"],
    "EINORS": ["IRONES", "SENIOR"], "EINPRS": ["RIPENS", "SNIPER"],
    "EINRST": ["INSERT", "INTERS", "SINTER"],
    # Level 5: 7-letter
    "ACELPRS": ["CLASPER", "PARCELS", "SCALPER"],
    "ADEGNRS": ["DANGERS", "GANDERS", "GARDENS"],
    "ADEINRS": ["RANDIES", "SARDINE"],
    "ADEINST": ["DETAINS", "INSTEAD", "SAINTED"],
    "AEGINRS": ["EARINGS", "ERASING", "REGAINS", "SEARING"],
    "AEGINST": ["INGESTA", "SEATING", "TEASING"],
    "AEGNRST": ["GARNETS", "STRANGE"],
    "AEILMNS": ["MENIALS", "SEMINAL"],
    "AEILMNT": ["AILMENT", "ALIMENT"],
    "AEILNRS": ["ALINERS", "NAILERS"],
    "AEILNST": ["ELASTIN", "ENTAILS", "SALTINE"],
    "AEINPRS": ["PANIERS", "RAPINES"],
    "AEINRST": ["NASTIER", "RETAINS", "STAINER"],
    "AEIPRST": ["PARTIES", "PASTIER", "PIRATES"],
    "AELMNOT": ["OMENTAL", "TELAMON"],
    "AELPRST": ["PLASTER", "PSALTER", "STAPLER"],
    "CEINORS": ["COINERS", "CRONIES", "ORCEINS"],
    "DEGILNS": ["DINGLES", "ENGILDS", "SINGLED"],
    "DEINORS": ["DINEROS", "INDORSE", "ORDINES", "ROSINED"],
    "EGILNRS": ["LINGERS", "SLINGER"],
    "EINORST": ["ORIENTS", "STONIER"],
    "AEGILNR": ["ALIGNER", "REALIGN"], "AEGLNR": ["ANGLER", "LANGER"],
}


def get_level_groups(level: int) -> dict[str, list[str]]:
    """Get anagram groups for a specific level."""
    target = level + 2
    if level == 5:
        return {k: v for k, v in ANAGRAM_GROUPS.items() if len(k) >= target}
    return {k: v for k, v in ANAGRAM_GROUPS.items() if len(k) == target}


# ══════════════════════════════════════════════════════════════
# Banking Engine — MDP Expected Value Optimizer
# ══════════════════════════════════════════════════════════════

class BankingEngine:
    """MDP banking engine using Expected Value calculations."""

    ACCURACY = {3: 0.98, 4: 0.95, 5: 0.92, 6: 0.88, 7: 0.85}

    def __init__(self) -> None:
        self.decisions_log: list[dict[str, Any]] = []

    def decide_bank_choice(
        self, level: int, guesses_left: int, words_remaining: int,
        _banked: int
    ) -> tuple[str, dict[str, Any]]:
        """Earn decision: 'preserve' or 'current'."""
        if guesses_left <= 1 and words_remaining > 1:
            ev_current = words_remaining * 0.5
            ev_preserve = 0.5 * self.ACCURACY.get(level + 2, 0.85)
            decision = "current" if ev_current > ev_preserve else "preserve"
            info = {
                "type": "earn", "decision": decision,
                "reason": f"Emergency: {guesses_left} guesses, {words_remaining} words",
                "ev_current": round(ev_current, 3),
                "ev_preserve": round(ev_preserve, 3),
            }
        else:
            ev_preserve = 0.5 * self.ACCURACY.get(level + 2, 0.85)
            decision = "preserve"
            info = {
                "type": "earn", "decision": "preserve",
                "reason": "Bank for future recovery",
                "ev_preserve": round(ev_preserve, 3),
            }
        self.decisions_log.append(info)
        return decision, info

    def decide_recovery(
        self, banked: int, failed_words: list[dict[str, Any]], levels_remaining: int
    ) -> tuple[bool, dict[str, Any] | None]:
        """Spend decision: attempt recovery?"""
        if banked <= 0 or not failed_words:
            return False, None

        target = min(failed_words, key=lambda fw: len(fw["word"]))
        word_len = len(target["word"])
        p_success = self.ACCURACY.get(word_len, 0.85)
        ev = p_success * 0.5 + (1 - p_success) * (-0.1)

        min_reserve = 1 if levels_remaining > 0 else 0
        can_spend = banked > min_reserve
        should_recover = ev > 0 and can_spend

        info = {
            "type": "spend", "decision": should_recover,
            "target_word": target["word"], "target_level": target["level"],
            "p_success": round(p_success, 2), "ev": round(ev, 3),
            "banked": banked, "reserve": min_reserve,
        }
        self.decisions_log.append(info)
        return should_recover, info


# ══════════════════════════════════════════════════════════════
# Game State + Session Manager
# ══════════════════════════════════════════════════════════════

class GameState:
    """Holds state for one game session."""

    def __init__(self) -> None:
        self.level: int = 1
        self.total_reward: float = 0.0
        self.banked_chances: int = 0
        self.failed_words: list[dict[str, Any]] = []
        self.level_results: list[dict[str, Any]] = []
        self.banker = BankingEngine()
        self.status: str = "created"  # created → playing → finished


# In-memory session store (UUID → GameState)
active_games: dict[str, GameState] = {}


# ══════════════════════════════════════════════════════════════
# SSE Event Stream — "Watch AI Play" (the core experience)
# ══════════════════════════════════════════════════════════════

async def ai_play_stream(game: GameState) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE events as the AI plays a full game.
    Each event is a JSON string with type + data for the frontend.
    """
    import json

    def sse(event_type: str, data: dict[str, Any]) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    game.status = "playing"
    yield sse("game_start", {"levels": 5, "total_groups": len(ANAGRAM_GROUPS)})

    for level in range(1, 6):
        groups = get_level_groups(level)
        if not groups:
            continue

        sorted_key = random.choice(list(groups.keys()))
        valid_words = groups[sorted_key]
        letters = list(sorted_key)
        random.shuffle(letters)
        max_guesses = len(valid_words) * 2

        yield sse("level_start", {
            "level": level,
            "letters": letters,
            "word_count": len(valid_words),
            "max_guesses": max_guesses,
            "bank": game.banked_chances,
        })

        # ── AI Thinking: analyzing the anagram ──
        yield sse("thinking", {
            "text": f"[System] Analyzing Target: {' '.join(letters)}...",
            "phase": "analyze",
        })
        await asyncio.sleep(0.3)

        yield sse("thinking", {
            "text": f"[LLM Solver] Extracting valid permutations...",
            "phase": "solve",
        })

        # ── Call Oracle ──
        try:
            guesses = await call_oracle(letters)
        except Exception as e:
            yield sse("error", {"message": f"Oracle error: {str(e)}"})
            guesses = []

        yield sse("thinking", {
            "text": f"[LLM Solver] Found: {', '.join(guesses)}",
            "phase": "result",
        })
        await asyncio.sleep(0.2)

        # ── Score the guesses ──
        found = []
        guesses_used = 0
        for w in guesses:
            guesses_used += 1
            if w in valid_words and w not in found:
                found.append(w)
                wrong_so_far = guesses_used - len(found)
                first_try = wrong_so_far == 0 and len(found) == 1

                if first_try:
                    game.total_reward += 1.0
                    yield sse("ai_guess", {
                        "word": w, "correct": True,
                        "first_try": True, "reward": 1.0,
                    })

                    # Banking decision (Level 3+)
                    if level >= 3:
                        guesses_left = max_guesses - guesses_used
                        words_left = len(valid_words) - len(found)
                        decision, info = game.banker.decide_bank_choice(
                            level, guesses_left, words_left, game.banked_chances
                        )

                        yield sse("thinking", {
                            "text": f"[Math Engine] Calculating EV... preserve={info.get('ev_preserve', '?')}",
                            "phase": "banking",
                        })
                        await asyncio.sleep(0.2)

                        if decision == "preserve":
                            game.banked_chances += 1
                            yield sse("bank_decision", {
                                "action": "earn_preserve",
                                "bank_total": game.banked_chances,
                                "ev": info.get("ev_preserve"),
                            })
                        else:
                            max_guesses += 2
                            yield sse("bank_decision", {
                                "action": "earn_current",
                                "extra_guesses": 2,
                                "ev": info.get("ev_current"),
                            })
                else:
                    game.total_reward += 0.5
                    yield sse("ai_guess", {
                        "word": w, "correct": True,
                        "first_try": False, "reward": 0.5,
                    })
            elif w not in found:
                yield sse("ai_guess", {
                    "word": w, "correct": False,
                    "first_try": False, "reward": 0,
                })

            await asyncio.sleep(0.15)  # pacing for visual effect

        # Track missed words
        missed = [w for w in valid_words if w not in found]
        for w in missed:
            game.failed_words.append({
                "word": w, "level": level, "letters": sorted_key,
            })

        all_found = len(missed) == 0
        if all_found:
            game.total_reward += 2.0

        game.level_results.append({
            "level": level, "correct": len(found),
            "total": len(valid_words), "all_found": all_found,
            "missed": missed, "answer_key": valid_words,
        })

        yield sse("level_end", {
            "level": level,
            "found": found, "missed": missed,
            "all_found": all_found,
            "reward_this_level": (1.0 if found else 0) + 0.5 * max(0, len(found) - 1) + (2.0 if all_found else 0),
            "total_reward": round(game.total_reward, 1),
        })

        # ── Level Pause: 10s so users can review AI answers ──
        yield sse("level_pause", {
            "duration": 10,
            "level_completed": level,
        })
        await asyncio.sleep(10)

        # ── Recovery Phase ──
        levels_remaining = 5 - level
        while game.failed_words and game.banked_chances > 0:
            should_recover, info = game.banker.decide_recovery(
                game.banked_chances, game.failed_words, levels_remaining
            )
            if not should_recover:
                break

            target = min(game.failed_words, key=lambda fw: len(fw["word"]))
            game.banked_chances -= 1
            recovery_letters = list(target["word"])
            random.shuffle(recovery_letters)

            yield sse("thinking", {
                "text": f"[Math Engine] Recovery EV = {info['ev']:+.3f} > 0. Spending bank...",
                "phase": "recovery",
            })
            await asyncio.sleep(0.3)

            yield sse("recovery_start", {
                "target_level": target["level"],
                "letters": recovery_letters,
                "bank_remaining": game.banked_chances,
            })

            # Call Oracle for recovery
            try:
                recovery_guesses = await call_oracle(recovery_letters)
            except Exception:
                recovery_guesses = []

            # Smart recovery: check if guess matches a failed word
            still_failed = {fw["word"] for fw in game.failed_words
                           if fw["letters"] == target["letters"]}
            recovered = None
            for g in recovery_guesses:
                if g in still_failed:
                    recovered = g
                    break

            if recovered:
                game.total_reward += 0.5
                game.failed_words = [
                    fw for fw in game.failed_words if fw["word"] != recovered
                ]
                yield sse("recovery_result", {
                    "success": True, "word": recovered,
                    "target_level": target["level"],
                    "reward": 0.5,
                })
            else:
                game.total_reward -= 0.1
                yield sse("recovery_result", {
                    "success": False, "target_word": target["word"],
                    "ai_guess": recovery_guesses[0] if recovery_guesses else "?",
                    "reward": -0.1,
                })
            await asyncio.sleep(0.2)

    # ── Perfect game check ──
    if not game.failed_words:
        game.total_reward += 5.0

    game.status = "finished"

    total_correct = sum(r["correct"] for r in game.level_results)
    total_possible = sum(r["total"] for r in game.level_results)

    yield sse("game_over", {
        "total_correct": total_correct,
        "total_possible": total_possible,
        "accuracy": round(total_correct / total_possible * 100, 1) if total_possible else 0,
        "total_reward": round(game.total_reward, 1),
        "perfect_game": len(game.failed_words) == 0,
        "bank_remaining": game.banked_chances,
        "decisions": game.banker.decisions_log,
    })


# ══════════════════════════════════════════════════════════════
# FastAPI Application
# ══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Anagram Quest — Game Master",
    description="FastAPI game server with SSE streaming for Watch AI Play",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health / Info ──
@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "Anagram Quest Game Master",
        "oracle": ORACLE_URL,
        "endpoints": {
            "stream": "GET /stream-ai-play",
            "match_create": "POST /match/create",
            "match_guess": "POST /match/{id}/guess",
            "match_ai": "GET /match/{id}/ai-stream",
            "health": "GET /health",
        },
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check — also pings the Oracle."""
    try:
        client = await _get_oracle_client()
        resp = await client.get(f"{ORACLE_URL}/health", timeout=6.0)
        oracle_ok = resp.status_code == 200
    except Exception:
        oracle_ok = False

    return {
        "game_master": "ok",
        "oracle": "ok" if oracle_ok else "unreachable",
        "active_games": len(active_games),
        "active_matches": len(active_matches),
        "oracle_cache_size": len(_oracle_cache),
    }


# ── SSE Stream: Watch AI Play ──
@app.get("/stream-ai-play")
async def stream_ai_play() -> StreamingResponse:
    """
    Start a new game and stream all events via SSE.

    The frontend connects via EventSource and receives:
    - game_start, level_start, thinking, ai_guess,
    - bank_decision, recovery_start, recovery_result,
    - level_end, game_over
    """
    game_id = str(uuid.uuid4())[:8]
    game = GameState()
    active_games[game_id] = game

    async def stream() -> AsyncGenerator[str, None]:
        try:
            async for event in ai_play_stream(game):
                yield event
        finally:
            # Clean up after game finishes or client disconnects
            if game_id in active_games:
                active_games[game_id].status = "finished"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Game-ID": game_id,
        },
    )


# ── Game Status (for polling / debug) ──
@app.get("/game/{game_id}")
async def get_game(game_id: str) -> dict[str, Any]:
    game = active_games.get(game_id)
    if not game:
        raise HTTPException(404, "Game not found")

    return {
        "game_id": game_id,
        "status": game.status,
        "level": game.level,
        "total_reward": round(game.total_reward, 1),
        "bank": game.banked_chances,
        "levels_completed": len(game.level_results),
    }


# ══════════════════════════════════════════════════════════════
# Match Engine — Player vs AI
# ══════════════════════════════════════════════════════════════

class MatchState:
    """State for a Player vs AI match."""

    def __init__(self) -> None:
        self.match_id: str = str(uuid.uuid4())[:8]
        self.status: str = "waiting"  # waiting → playing → finished
        self.current_level: int = 0
        self.levels_data: list[dict[str, Any]] = []
        self.human_score: float = 0.0
        self.human_bank: int = 0
        self.human_found: dict[int, list[str]] = {}
        self.human_guesses: dict[int, int] = {}
        self.human_missed_words: list[dict[str, Any]] = []
        self.human_bank_log: list[dict[str, Any]] = []
        self.ai_score: float = 0.0
        self.ai_bank: int = 0
        self.ai_found: dict[int, list[str]] = {}
        self.ai_missed_words: list[dict[str, Any]] = []
        self.ai_bank_log: list[dict[str, Any]] = []
        self.ai_banker = BankingEngine()
        self.ai_guesses: dict[int, list[str]] = {}
        self.ai_guess_cursor: dict[int, int] = {}
        self.ai_completion_awarded: set[int] = set()
        self.level_results: list[dict[str, Any]] = []
        self.created_at: float = time.time()
        self.last_active: float = time.time()

        # Pre-generate 5 levels of letters
        for level in range(1, 6):
            groups = get_level_groups(level)
            if not groups:
                continue
            sorted_key = random.choice(list(groups.keys()))
            valid_words = groups[sorted_key]
            letters = list(sorted_key)
            random.shuffle(letters)
            self.levels_data.append({
                "level": level,
                "sorted_key": sorted_key,
                "letters": letters,
                "valid_words": valid_words,
            })

    def touch(self) -> None:
        self.last_active = time.time()


# In-memory match store
active_matches: dict[str, MatchState] = {}


class GuessRequest(BaseModel):
    word: str
    level: int | None = None


def _pick_recovery_target(missed_words: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not missed_words:
        return None
    return min(missed_words, key=lambda item: len(str(item.get("word", ""))))


def _run_recovery(
    score: float,
    missed_words: list[dict[str, Any]],
) -> tuple[bool, float, dict[str, Any] | None, float]:
    """Run one stochastic recovery attempt using BankingEngine accuracy priors."""
    target = _pick_recovery_target(missed_words)
    if not target:
        return False, score, None, 0.0

    word = str(target["word"])
    p_success = BankingEngine.ACCURACY.get(len(word), 0.85)
    if random.random() <= p_success:
        updated_score = score + 0.5
        missed_words.remove(target)
        return True, updated_score, target, p_success

    updated_score = max(0.0, score - 0.1)
    return False, updated_score, target, p_success


@app.post("/match/create")
async def create_match() -> dict[str, Any]:
    """Create a new Player vs AI match."""
    match = MatchState()
    if not match.levels_data:
        raise HTTPException(500, "No level data configured")

    match.current_level = 1
    match.status = "playing"
    active_matches[match.match_id] = match

    level_data = match.levels_data[0]
    match.human_found[1] = []
    match.human_guesses[1] = 0
    match.ai_found[1] = []

    return {
        "match_id": match.match_id,
        "level": 1,
        "letters": level_data["letters"],
        "word_count": len(level_data["valid_words"]),
        "total_levels": len(match.levels_data),
        "human_bank": match.human_bank,
        "ai_bank": match.ai_bank,
    }


@app.post("/match/{match_id}/guess")
async def match_guess(match_id: str, req: GuessRequest) -> dict[str, Any]:
    """Validate a human player's guess."""
    match = active_matches.get(match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != "playing":
        raise HTTPException(400, "Match not active")

    match.touch()
    level = match.current_level
    if level < 1 or level > len(match.levels_data):
        raise HTTPException(400, "Invalid match level")

    level_data = match.levels_data[level - 1]
    word = req.word.upper().strip()

    # Ignore in-flight guesses from a previous level transition.
    if req.level is not None and req.level != level:
        return {
            "valid": False,
            "reason": "stale_level",
            "word": word,
            "reward": 0,
            "submitted_level": req.level,
            "active_level": level,
            "human_bank": match.human_bank,
        }

    # Initialize level tracking if needed
    if level not in match.human_found:
        match.human_found[level] = []
        match.human_guesses[level] = 0

    match.human_guesses[level] = match.human_guesses.get(level, 0) + 1

    # Already found this word?
    if word in match.human_found[level]:
        return {
            "valid": False,
            "reason": "already_found",
            "word": word,
            "reward": 0,
            "human_bank": match.human_bank,
        }

    # Is it a valid word for this level?
    if word in level_data["valid_words"]:
        is_first_guess = match.human_guesses[level] == 1 and len(match.human_found[level]) == 0
        reward = 1.0 if is_first_guess else 0.5
        match.human_score += reward
        match.human_found[level].append(word)

        bank_awarded = False
        bank_event: dict[str, Any] | None = None
        if level >= 3 and is_first_guess:
            match.human_bank += 1
            bank_awarded = True
            bank_event = {
                "type": "earn_preserve",
                "by": "human",
                "level": level,
                "delta": 1,
                "bank_total": match.human_bank,
                "reason": "first_try_level3_plus",
            }
            match.human_bank_log.append(bank_event)

        all_found = len(match.human_found[level]) == len(level_data["valid_words"])
        if all_found:
            match.human_score += 2.0  # Completion bonus

        return {
            "valid": True,
            "word": word,
            "reward": reward,
            "first_try": is_first_guess,
            "human_score": round(match.human_score, 1),
            "human_bank": match.human_bank,
            "found_count": len(match.human_found[level]),
            "total_words": len(level_data["valid_words"]),
            "all_found": all_found,
            "bank_awarded": bank_awarded,
            "bank_event": bank_event,
        }
    else:
        return {
            "valid": False,
            "reason": "wrong",
            "word": word,
            "reward": 0,
            "human_bank": match.human_bank,
        }


@app.post("/match/{match_id}/bank/boost")
async def match_bank_boost(match_id: str) -> dict[str, Any]:
    """Spend 1 bank to boost current score (+0.5)."""
    match = active_matches.get(match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != "playing":
        raise HTTPException(400, "Match not active")
    if match.current_level < 3:
        raise HTTPException(400, "Bank actions unlock at level 3")
    if match.human_bank <= 0:
        raise HTTPException(400, "No bank available")

    match.touch()
    match.human_bank -= 1
    match.human_score += 0.5
    event = {
        "type": "spend_current",
        "by": "human",
        "level": match.current_level,
        "delta": -1,
        "reward": 0.5,
        "bank_total": match.human_bank,
    }
    match.human_bank_log.append(event)
    return {
        "ok": True,
        "action": "boost_current",
        "reward": 0.5,
        "human_score": round(match.human_score, 1),
        "human_bank": match.human_bank,
        "bank_event": event,
    }


@app.post("/match/{match_id}/bank/recover")
async def match_bank_recover(match_id: str) -> dict[str, Any]:
    """Spend 1 bank to attempt recovery of one previously missed word."""
    match = active_matches.get(match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    if match.status != "playing":
        raise HTTPException(400, "Match not active")
    if match.current_level < 3:
        raise HTTPException(400, "Bank actions unlock at level 3")
    if match.human_bank <= 0:
        raise HTTPException(400, "No bank available")
    if not match.human_missed_words:
        raise HTTPException(400, "No missed words to recover")

    match.touch()
    match.human_bank -= 1
    success, updated_score, target, p_success = _run_recovery(
        score=match.human_score,
        missed_words=match.human_missed_words,
    )
    match.human_score = updated_score

    event = {
        "type": "recover",
        "by": "human",
        "level": match.current_level,
        "delta": -1,
        "success": success,
        "p_success": round(p_success, 2),
        "target_word": target["word"] if target else None,
        "bank_total": match.human_bank,
        "reward": 0.5 if success else -0.1,
    }
    match.human_bank_log.append(event)

    return {
        "ok": True,
        "action": "recover",
        "success": success,
        "reward": 0.5 if success else -0.1,
        "p_success": round(p_success, 2),
        "target_word": target["word"] if target else None,
        "target_level": target["level"] if target else None,
        "human_score": round(match.human_score, 1),
        "human_bank": match.human_bank,
        "bank_event": event,
    }


@app.post("/match/{match_id}/next-level")
async def match_next_level(match_id: str) -> dict[str, Any]:
    """Advance to the next level."""
    match = active_matches.get(match_id)
    if not match:
        raise HTTPException(404, "Match not found")

    match.touch()
    current = match.current_level
    if current < 1 or current > len(match.levels_data):
        raise HTTPException(400, "Invalid match level")

    # Record level result
    level_data = match.levels_data[current - 1]
    valid_words = level_data["valid_words"]
    human_found = match.human_found.get(current, [])
    ai_found = match.ai_found.get(current, [])
    human_missed = [word for word in valid_words if word not in human_found]
    ai_missed = [word for word in valid_words if word not in ai_found]

    for word in human_missed:
        match.human_missed_words.append({
            "word": word,
            "level": current,
            "letters": level_data["sorted_key"],
        })
    for word in ai_missed:
        match.ai_missed_words.append({
            "word": word,
            "level": current,
            "letters": level_data["sorted_key"],
        })

    match.level_results.append({
        "level": current,
        "human_found": human_found,
        "human_count": len(human_found),
        "human_missed": human_missed,
        "ai_found": ai_found,
        "ai_count": len(ai_found),
        "ai_missed": ai_missed,
        "total_words": len(valid_words),
        "human_bank": match.human_bank,
        "ai_bank": match.ai_bank,
        "winner": "human" if len(human_found) > len(ai_found) else ("ai" if len(ai_found) > len(human_found) else "tie"),
    })

    # Check if game is over
    if current >= len(match.levels_data):
        match.status = "finished"
        human_wins = sum(1 for r in match.level_results if r["winner"] == "human")
        ai_wins = sum(1 for r in match.level_results if r["winner"] == "ai")
        return {
            "game_over": True,
            "level_results": match.level_results,
            "human_score": round(match.human_score, 1),
            "ai_score": round(match.ai_score, 1),
            "human_bank": match.human_bank,
            "ai_bank": match.ai_bank,
            "human_bank_log": match.human_bank_log[-12:],
            "ai_bank_log": match.ai_bank_log[-12:],
            "winner": "human" if human_wins > ai_wins else ("ai" if ai_wins > human_wins else "tie"),
            "human_levels_won": human_wins,
            "ai_levels_won": ai_wins,
        }

    # Advance
    match.current_level = current + 1
    next_data = match.levels_data[current]  # 0-indexed
    match.human_found[current + 1] = []
    match.human_guesses[current + 1] = 0
    match.ai_found[current + 1] = []

    return {
        "game_over": False,
        "level": current + 1,
        "letters": next_data["letters"],
        "word_count": len(next_data["valid_words"]),
        "human_bank": match.human_bank,
        "ai_bank": match.ai_bank,
        "human_bank_log": match.human_bank_log[-8:],
        "ai_bank_log": match.ai_bank_log[-8:],
        "level_results": match.level_results,
    }


@app.get("/match/{match_id}/ai-stream")
async def match_ai_stream(match_id: str) -> StreamingResponse:
    """
    SSE stream for the AI side of a Player vs AI match.
    AI solves via Oracle and drip-feeds results on a fast PvAI cadence.
    """
    match = active_matches.get(match_id)
    if not match:
        raise HTTPException(404, "Match not found")

    import json

    def sse(event_type: str, data: dict[str, Any]) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    async def stream() -> AsyncGenerator[str, None]:
        match.touch()
        level = match.current_level
        level_data = match.levels_data[level - 1]
        letters = level_data["letters"]
        valid_words = level_data["valid_words"]
        max_guesses = max(2, len(valid_words) * 2)

        # Fast auto-recovery keeps banking strategic without slowing PvAI rounds.
        if level >= 3 and match.ai_bank > 0 and match.ai_missed_words:
            should_recover, info = match.ai_banker.decide_recovery(
                banked=match.ai_bank,
                failed_words=match.ai_missed_words,
                levels_remaining=max(0, len(match.levels_data) - level),
            )
            if should_recover:
                match.ai_bank -= 1
                success, updated_score, target, p_success = _run_recovery(
                    score=match.ai_score,
                    missed_words=match.ai_missed_words,
                )
                match.ai_score = updated_score
                event = {
                    "type": "recover",
                    "by": "ai",
                    "level": level,
                    "delta": -1,
                    "success": success,
                    "target_word": target["word"] if target else None,
                    "bank_total": match.ai_bank,
                    "reward": 0.5 if success else -0.1,
                    "ev": round(info["ev"], 3) if info else None,
                    "p_success": round(p_success, 2),
                }
                match.ai_bank_log.append(event)
                yield sse("ai_thinking", {
                    "text": (
                        f"[MDP Bank] Recovery {'success' if success else 'failed'} "
                        f"for {event['target_word']} ({event['reward']:+.1f})"
                    ),
                    "phase": "banking",
                })

        yield sse("ai_thinking", {
            "text": f"[System] Analyzing: {' '.join(letters)}...",
            "phase": "analyze",
        })
        await asyncio.sleep(0.1)

        yield sse("ai_thinking", {
            "text": "[LLM Solver] Extracting valid permutations...",
            "phase": "solve",
        })

        # Cache oracle candidates by level so reconnects resume deterministically.
        if level not in match.ai_guesses:
            raw_guesses: list[str] = []
            try:
                raw_guesses = await asyncio.wait_for(call_oracle(letters), timeout=6.0)
            except asyncio.TimeoutError:
                yield sse("ai_thinking", {
                    "text": "[NET] Oracle timeout; switching to local solver cache.",
                    "phase": "net",
                })
            except Exception as exc:
                yield sse("ai_thinking", {
                    "text": f"[NET] Oracle unavailable ({str(exc)[:70]}). Using local solver cache.",
                    "phase": "net",
                })

            seen: set[str] = set()
            normalized: list[str] = []
            for guess in raw_guesses:
                word = str(guess).upper().strip()
                if not word or word in seen:
                    continue
                seen.add(word)
                normalized.append(word)

            if not normalized:
                # Fallback prevents PvAI stalls when Oracle is slow/unreachable.
                normalized = list(valid_words)
                random.shuffle(normalized)

            valid_set = set(valid_words)
            ordered_valid = [word for word in normalized if word in valid_set]
            ordered_decoys = [
                word for word in normalized if word not in valid_set
            ][: max(1, len(valid_words) // 2)]
            match.ai_guesses[level] = ordered_valid + ordered_decoys
            match.ai_guess_cursor[level] = 0

        ai_guesses = match.ai_guesses[level]

        yield sse("ai_thinking", {
            "text": f"[LLM Solver] Found {len(ai_guesses)} candidates",
            "phase": "result",
        })
        await asyncio.sleep(0.12)

        if level not in match.ai_found:
            match.ai_found[level] = []

        if not ai_guesses:
            yield sse("ai_thinking", {
                "text": "[LLM Solver] No valid candidates this round.",
                "phase": "result",
            })

        # Drip-feed scored results; resume from previous cursor on SSE reconnect.
        start_idx = match.ai_guess_cursor.get(level, 0)
        for idx in range(start_idx, len(ai_guesses)):
            match.touch()
            if match.status != "playing":
                break
            if len(match.ai_found[level]) >= len(valid_words):
                break

            word = ai_guesses[idx]
            match.ai_guess_cursor[level] = idx + 1

            if word in match.ai_found[level]:
                continue

            if word in valid_words:
                is_first = len(match.ai_found[level]) == 0
                reward = 1.0 if is_first else 0.5
                match.ai_score += reward
                match.ai_found[level].append(word)

                bank_event: dict[str, Any] | None = None
                if level >= 3 and is_first:
                    guesses_left = max(0, max_guesses - (idx + 1))
                    words_remaining = len(valid_words) - len(match.ai_found[level])
                    decision, info = match.ai_banker.decide_bank_choice(
                        level=level,
                        guesses_left=guesses_left,
                        words_remaining=words_remaining,
                        _banked=match.ai_bank,
                    )
                    if decision == "preserve":
                        match.ai_bank += 1
                        bank_event = {
                            "type": "earn_preserve",
                            "by": "ai",
                            "level": level,
                            "delta": 1,
                            "bank_total": match.ai_bank,
                            "ev": info.get("ev_preserve"),
                        }
                    else:
                        match.ai_score += 0.5
                        bank_event = {
                            "type": "spend_current",
                            "by": "ai",
                            "level": level,
                            "delta": 0,
                            "bank_total": match.ai_bank,
                            "ev": info.get("ev_current"),
                            "reward": 0.5,
                        }
                    match.ai_bank_log.append(bank_event)
                    yield sse("ai_thinking", {
                        "text": (
                            f"[MDP Bank] {'Preserve +1 bank' if decision == 'preserve' else 'Boost current +0.5'} "
                            f"(EV {bank_event.get('ev', '?')})"
                        ),
                        "phase": "banking",
                    })

                yield sse("ai_guess", {
                    "word": word,
                    "correct": True,
                    "first_try": is_first,
                    "reward": reward,
                    "ai_score": round(match.ai_score, 1),
                    "found_count": len(match.ai_found[level]),
                    "ai_bank": match.ai_bank,
                    "bank_event": bank_event,
                })
            else:
                yield sse("ai_guess", {
                    "word": word,
                    "correct": False,
                    "reward": 0,
                    "ai_bank": match.ai_bank,
                })

            # Fast cadence keeps PvAI competitive without waiting on long delays.
            await asyncio.sleep(random.uniform(0.2, 0.45))

        found_words = match.ai_found[level]
        all_found = len(found_words) == len(valid_words)
        if all_found and level not in match.ai_completion_awarded:
            match.ai_score += 2.0
            match.ai_completion_awarded.add(level)

        yield sse("ai_level_done", {
            "level": level,
            "found": found_words,
            "total": len(valid_words),
            "all_found": all_found,
            "ai_score": round(match.ai_score, 1),
            "ai_bank": match.ai_bank,
            "ai_bank_log": match.ai_bank_log[-8:],
        })

        match.touch()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.get("/match/{match_id}/status")
async def match_status(match_id: str) -> dict[str, Any]:
    """Get current match state."""
    match = active_matches.get(match_id)
    if not match:
        raise HTTPException(404, "Match not found")
    return {
        "match_id": match.match_id,
        "status": match.status,
        "current_level": match.current_level,
        "human_score": round(match.human_score, 1),
        "human_bank": match.human_bank,
        "human_bank_log": match.human_bank_log[-8:],
        "human_missed_count": len(match.human_missed_words),
        "ai_score": round(match.ai_score, 1),
        "ai_bank": match.ai_bank,
        "ai_bank_log": match.ai_bank_log[-8:],
        "ai_missed_count": len(match.ai_missed_words),
        "level_results": match.level_results,
    }


# ── Garbage Collection ──
@app.on_event("startup")
async def start_gc() -> None:
    async def gc_loop() -> None:
        while True:
            await asyncio.sleep(GC_INTERVAL_SECONDS)
            now = time.time()
            expired: list[str] = []
            for match_id, match in list(active_matches.items()):
                ttl = (
                    MATCH_TTL_PLAYING_SECONDS
                    if match.status == "playing"
                    else MATCH_TTL_IDLE_SECONDS
                )
                if now - match.last_active > ttl:
                    expired.append(match_id)

            for match_id in expired:
                del active_matches[match_id]

    asyncio.create_task(gc_loop())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await _close_oracle_client()


# ══════════════════════════════════════════════════════════════
# Entrypoint
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
