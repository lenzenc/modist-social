# Modist Social

A simulated craft-brewery taproom. Patrons, bartenders and walk-ins are AI characters whose dialogue is written by **Claude Haiku** (`claude-haiku-5-5`). A deterministic Python director runs everything else. See README.md for the full feature list.

## Where AI is used, and where it isn't

This split matters when planning or building a feature. Decide which side it belongs on and say so.

**Deterministic Python (costs no tokens):** the director and clock (`backend/app/sim/`), arrivals, seating, bartender roster, drinks and sales, weather, game and trivia schedule, conversation orchestration, budget guard. Prefer code for anything that doesn't need language.

**Haiku calls (cost money, go through `backend/app/llm/`):**
- `speak`: one person's next line or action (chat, order, staff).
- `summarize`: short memory summaries.
- `news`: the daily local-headlines search.
- Newcomer generation: the prose parts of a walk-in's profile (code rolls the name, age, scores and schedule).
- God Mode event scoring: reach, divisiveness, sides and each person's stance.

Everything LLM-related goes through the `LLM` protocol in `backend/app/llm/types.py`. Don't call the Anthropic SDK from anywhere else.

## Rules for LLM work

- **Every LLM feature must also work in mock mode** (`LLM_MODE=mock`, `backend/app/llm/mock.py`). Extend `MockLLM` and `TurnRequest` fields (mock-only fields are marked in `types.py`) so `make mock` still runs the whole flow for $0 and tests stay offline. Never make tests call the live API.
- **Keep token use low.** Haiku, thinking off, `effort: low`, JSON output capped at 300 tokens. Prompt order is cache-friendly: world bible, then persona (both `cache_control`), then a small volatile scene. Don't put volatile content ahead of the cacheable prefix.
- **Cost is tracked** in `app/llm/usage.py` with prices in `app/config.py`. New calls must be counted and respect `MAX_CONCURRENT_LLM` and `DAILY_BUDGET_USD`.
- The model ID lives in `settings.model` (`app/config.py`). Don't hardcode it elsewhere.
- Prompts are in `backend/app/agents/prompts.py`; persona and world content is in `backend/app/seed/` (`world.md`, `patrons.yaml`, etc.).
- Persona edits apply on restart. Adding people or changing relationships needs `make reset`, which wipes all data including walk-ins.

## Commands

Python always runs through `uv` (`uv run`, `uv add`).

- `make mock`: run the full app with canned dialogue, no API key needed.
- `make dev`: run live (needs `ANTHROPIC_API_KEY` in `.env`).
- `make test`: backend unit tests (`cd backend && uv run pytest -q`).
- `make reset`: wipe data and start fresh.

## Layout

Backend: FastAPI + SQLAlchemy (async) + Postgres. `app/sim` (director, clock, schedule, seating), `app/agents` (prompts, turns, memory), `app/llm` (live and mock clients, usage). Frontend: React + Vite + Tailwind + Zustand, using `/api` and `/ws`.

## Git

Commit directly to `master`. Don't create a branch (or open a PR) unless I say so.
