# Next 10 features for realism

Here are the 10 features I'd build next, ranked by how much they add to the goal of people who feel human. I picked them from what the README says exists and what's missing. I haven't read the code beyond the file list, so check each against the code before committing.

The simulation already has moods, buzz, memory, relationships and gossip. The remaining gaps are mostly these:
- Nothing changes between visits.
- Relationships never turn into anything.
- Everyone talks in a similar voice.
- There's no way to tell when realism slips.

1. **Realism scorecard and repetition detector.** Measure the sameness that LLM patrons drift into: repeated openers, the same topics night after night, similar sentence shapes across different people, and conversations that wrap up too neatly. Report it on a dashboard and feed it back as a "don't say this again" list in the prompts. This goes first because it tells you whether the other nine are working.

2. **Life between visits.** Today, "life lately" shifts a little after each reflection. Give each patron an off-screen life instead. Each sim day, a cheap or deterministic roll gives some of them a work event, a family or health event, money trouble or good news. They arrive already carrying it ("my car died Tuesday"), and it affects mood, how long they stay and how much they drink. This gives people a continuous existence.

3. **Evolving relationships.** Familiarity and affinity are only two numbers right now. Add named relationship types that form and change: friends, close friends, rivals, a crush, a couple, a falling-out, a mentor. Give each type its own behavior, such as sitting together, teasing, avoiding each other or making up. A date, a breakup or a grudge that lasts weeks is among the most human things the room could show.

4. **Drunkenness with consequences.** Buzz already exists but doesn't change much beyond looser chat. Add:
   - Bartenders who slow down or cut off a guest.
   - Slurred or sloppy speech, and louder talk.
   - A regret-the-next-day memory.
   - Switching to water.
   - A rideshare or designated driver at the end of the night.
   - Occasional sloppy moments: a dropped glass, an overshared secret.

5. **Gossip with provenance and distortion.** Third-party memories resurface now, but they don't record who said what. Track each rumor's source and how confident the teller was. Let it mutate a little as it's retold. Let people be wrong or caught out, and let the subject hear what's being said about them. That creates real social consequences.

6. **Physical and non-verbal behavior.** Everything is speech right now. Add short action beats: checking a phone, glancing at the TV, waving across the room, picking a song on the jukebox, stepping out to take a call or have a smoke. Add awkward silences and people leaving a chat mid-sentence. Real taprooms are mostly not talking, and this fills the gaps.

7. **Taste and habits that evolve.** Give each patron favorite drinks that shift. A patron tries something new on a bartender's recommendation, orders the same thing every time, or gets tired of a beer. Add budgets, so some people skip a round when money is tight and others buy rounds for friends. This makes the sales data and the bartender interactions more believable.

8. **Group dynamics inside conversations.** Conversations are currently a set of turns. Add:
   - Cliques and subgroups that split off.
   - A third wheel who goes quiet.
   - Someone who dominates or interrupts.
   - A joke that lands with one person and not the rest.
   - Shared emotional mood across a table.
   - People who deliberately steer a chat to a new topic.

9. **Bartender inner lives.** Bartenders mostly respond to guests. Give them moods, fatigue over a shift, mistakes (wrong order, a spill), a rough night, opinions about regulars, a favorite and a pet peeve, and a bit of friction with each other. They are the constant presence in the room, so they have a large effect on how real it feels.

10. **Calendar events and traditions.** Weather, the game and trivia are already there. Add holidays, birthdays (someone gets bought a round), a regular's last night before moving away, a new beer release, a private party or live music, a slow Tuesday versus a loud Saturday. These give the room a rhythm and give patrons shared things to talk about and remember. Have the room's history accumulate: "the night the power went out."

**Suggested order.** Build 1 first so you can see the effect of everything else. Then 2 and 3 together, since off-screen events feed relationship changes. Then 4 and 5, which each depend on earlier work and add stakes. Items 6 to 10 can follow in any order.
