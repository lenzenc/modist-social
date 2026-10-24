# ui-awesome: three ways to watch the taproom

Three experimental views for answering "who is where, how are they doing, and what are they saying". They are separate pages on the same live simulation, so you can compare them with the same crowd. The Slack-style chat at `/` and the 3D floor at `/taproom` are untouched.

| Page | What it is for |
|---|---|
| `/watch` | All three side by side, live, each with an "Open full screen" link. |
| `/watch/tower` | **Tower.** Air-traffic control for a bar. Conversations are flight strips; around them sit a floor plan, a roster and a timeline. |
| `/watch/taps` | **Taps.** A wall of every live conversation, one column each, tinted by what it's about. |
| `/watch/ledger` | **Ledger.** The night as one ruled row per person, time running across. |

![Tower](screenshots/watch-tower.jpg)

## Tower

- **Floor** in plan view with five lenses that colour each person: mood, buzz, energy, ties and topic. Conversations are outlined on the floor; a heated one (opposing sides, building tension) pulses.
- **Ties** draws lines from the person you pick to everyone they know who is here: green for people they get on with, red for friction, thicker for closer.
- **Roster** by zone with mood, buzz and energy at a glance, a search box, a "Worth a look" filter (cut off, drunk, worn out, low mood), and pins that stay on top.
- **Live conversations** as strips, coloured like flight strips: buff for a chat, blue for an order, pink for a heated one. Click a strip to listen in: up to three transcripts stream in the dock.
- **Follow a person** with a double-click. The camera zooms to them, their conversation joins the dock and their latest line shows as a subtitle.
- **Timeline** of the night: headcount, room mood, arrivals and departures, and the God Mode event as a red line.

![Taps](screenshots/watch-taps.jpg)

## Taps

- Every live chat is a column. Its colour is the topic on the beer colour scale: paler for light talk (small talk, stories, life), amber for beer, copper for town, sports and culture, brown for gossip, stout for city hall and the God Mode event. Darker means heavier.
- Each column header has a tiny seat map (which stools or which table), the vibe (lively, easy, flat, tense) and the line count. Columns stay put while you read; ones that go quiet fade and drift to the end.
- Columns are as tall as what's been said, like a glass filling.
- Click a name for a slide-over with mood, buzz, energy, private thought, who they know and what they remember. Star conversations and use "Only starred" to listen to just those.

![Ledger](screenshots/watch-ledger.jpg)

## Ledger

- One row per person, ordered by arrival (or longest stay, mood, buzz, name). A solid bar is a conversation, a pale bar is time on their own; the colour is the place (bar, inside tables, patio, in line).
- Round beads are drinks. A red mark above the bar is a need (restroom, phone call, air); a cross is a cut-off. Under each bar, a thin colour line is mood and below it buzz.
- Click a solid bar to read that conversation at any point in the night. Click a name for a chart of their mood, buzz and energy over the night.

## What the backend adds

All deterministic, no model calls, and it works in `make mock`:

- **Presence** now carries each person's mood, buzz, battery, need, whether they're busy and whether they've been cut off. It is broadcast after each spoken line, at most once per 0.75 s of real time.
- **Thread events** carry the table's vibe, tension, topic (read from the last few lines with the existing `realism.topic_of`), who is on the outside and what chat it split from.
- **`GET /api/tonight`** returns the night so far: every 5 sim minutes while open, where everyone was (place, conversation) and how they felt (mood, buzz, battery, drinks, need, cut off), plus the door log. It resets at opening. This is what lets a view opened mid-evening show the whole night.

## Running it

It lives in its own worktree so it doesn't collide with the main checkout:

```bash
cd ~/dev/modist-social-awesome
docker exec modist-social-db-1 psql -U modist -d postgres -c "CREATE DATABASE modist_awesome"   # once
cd backend && LLM_MODE=mock DATABASE_URL=postgresql+asyncpg://modist:modist@localhost:5433/modist_awesome uv run uvicorn app.main:app --port 8002
cd frontend && BACKEND_URL=http://localhost:8002 npm run dev -- --port 5175
```

Then open http://localhost:5175/watch. Set Crowd to Busy or Packed and raise the speed to see a full room; Fridays and Saturdays are busiest.

## Notes

- At high sim speeds the socket delivers dozens of events a second, so the watch views read from the store through `useThrottled` (`watch/shared/useThrottled.ts`) and redraw a few times a second.
- Colours for mood, buzz and energy are shared (`watch/shared/scales.ts`) so the same feeling reads the same in all three.
