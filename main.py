"""
Anagram Quest — Game Master Server (Phase 4b)

FastAPI backend with:
  - GameEngine: 5-level game state machine
  - BankingEngine: MDP-based Expected Value optimizer
  - OracleClient: Async HTTP calls to HF Spaces LLM
  - SSE streaming: Real-time "AI Thinking" events for the frontend
"""

import uuid
import random
import asyncio
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ══════════════════════════════════════════════════════════════
# Oracle Client — Async calls to HF Spaces LLM
# ══════════════════════════════════════════════════════════════
ORACLE_URL = "https://ailanidivyansh-anagram-quest-oracle.hf.space"


async def call_oracle(letters: list[str]) -> list[str]:
    """Call the HF Spaces Oracle to solve an anagram."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{ORACLE_URL}/solve",
            json={"letters": letters},
        )
        resp.raise_for_status()
        return resp.json()["words"]


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


def get_level_groups(level: int) -> dict:
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

    def __init__(self):
        self.decisions_log = []

    def decide_bank_choice(
        self, level: int, guesses_left: int, words_remaining: int,
        banked: int
    ) -> tuple[str, dict]:
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
        self, banked: int, failed_words: list, levels_remaining: int
    ) -> tuple[bool, dict | None]:
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

    def __init__(self):
        self.level = 1
        self.total_reward = 0.0
        self.banked_chances = 0
        self.failed_words = []
        self.level_results = []
        self.banker = BankingEngine()
        self.status = "created"  # created → playing → finished


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

    def sse(event_type: str, data: dict) -> str:
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
async def root():
    return {
        "service": "Anagram Quest Game Master",
        "oracle": ORACLE_URL,
        "endpoints": {
            "stream": "GET /stream-ai-play",
            "status": "GET /game/{game_id}",
            "health": "GET /health",
        },
    }


@app.get("/health")
async def health():
    """Health check — also pings the Oracle."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{ORACLE_URL}/health")
            oracle_ok = resp.status_code == 200
    except Exception:
        oracle_ok = False

    return {
        "game_master": "ok",
        "oracle": "ok" if oracle_ok else "unreachable",
        "active_games": len(active_games),
    }


# ── SSE Stream: Watch AI Play ──
@app.get("/stream-ai-play")
async def stream_ai_play():
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

    async def stream():
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
async def get_game(game_id: str):
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
# Entrypoint
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
