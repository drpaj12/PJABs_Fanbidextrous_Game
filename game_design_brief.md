# PJAB's Fanbidextrous Game — Design Brief

*A document for game designers. It describes what the game must be built around,
not what the game is. The actual mechanics, theme, win conditions, prediction types,
and feel are yours to invent within these constraints.*

---

## What This Game Is, In Plain Language

Two people watch the same live professional sports game — NHL hockey or FIFA World Cup
soccer. Before the game starts, each person builds a hand of cards representing real
athletes who are actually playing that day. During the game, on a fixed two-minute cycle,
each player commits to a prediction about what will happen next in the real game. When
the next cycle arrives, the results of the previous predictions are revealed and resolved.
What those predictions are, how cards interact with them, how points work, and whether
the players are competing, cooperating, or not even playing at the same time — all of
that is yours to design.

That is the skeleton. Everything else is the design problem.

---

## The Hard Constraints

These are not suggestions. They are the edges of the box the game must fit inside. They
come from technical and architectural decisions that are already made and cannot change
without rebuilding the foundation.

---

### Constraint 1: The Two-Minute Heartbeat

The game runs on a fixed 120-second cycle. Every two minutes, the game checks a live
sports data feed and learns what real events occurred during the previous window — a goal,
a penalty, a hit, a card. This is not a choice. It is the polling rate of the data feed,
chosen to stay within free API rate limits while still feeling responsive.

**The critical timing rule:** Predictions must be submitted before the next two-minute
window opens. The results of those predictions are not revealed until after the following
window begins. This means players are always predicting blind — you commit to what you
think will happen, the window closes, the real events occur, and only when the next window
opens do you learn whether you were right. You cannot watch events unfold and then predict
them. The prediction is always ahead of the knowledge.

**What this means for design:**

The two-minute window is the fundamental unit of time in the game. Everything a player
does — submitting a prediction, playing a card, activating an ability — must be designed
to happen within one window or explicitly across multiple. The designer cannot create
mechanics that require faster feedback than two minutes, because the data does not arrive
faster than that.

The timing also creates a specific emotional texture: commit without knowing, wait while
the real world does what it does, then discover. The gap between prediction and resolution
is where the tension lives. The game should be designed to make that gap feel charged
rather than empty.

---

### Constraint 2: Cards Come From the Real Lineup

Before the game starts, the system queries the actual sports API and retrieves the real
roster of players who are confirmed to be playing that day. That list — and only that
list — is the pool from which players build their hands. There are no fictional athletes,
no made-up teams, no generic placeholders.

**What this means for design:**

Cards are grounded in reality. Auston Matthews, if he is playing tonight, is a card.
Alphonso Davies, if Canada is in a World Cup match today, is a card. Their in-game value
must be tied somehow to what they actually do in real sports — their position, their role,
their team, or whatever the designer chooses to express. But the pool is always the real
day's players.

The card pool changes every session. No two games have the same set of available athletes.
The designer must account for a game where neither player knows exactly which athletes will
be available until they sit down to play. The pool is split across two teams. Whether team
affiliation matters mechanically is a design decision.

---

### Constraint 3: The Only Things Transmitted Are Drafts and Predictions

The two players are on separate devices. The only information that travels between them
is the draft selections each player makes before the game, and the prediction each player
submits for each window during the game. Everything else — scores, game state, animations,
card resolution — is computed locally on each device from data that both devices already
share: the live sports feed and a random seed established at session start.

**The draft transmission:** Both players draft from the same pool. Unlike a traditional
trading card game draft, both players may select the same athlete — there is no exclusivity
enforced by the architecture. Whether the designer wants to allow duplicate picks, penalize
them, or forbid them is a mechanical decision, but the infrastructure does not prevent two
players from holding the same card. Draft picks are transmitted to the relay so each client
knows what the opponent holds.

**The prediction transmission:** Each player's prediction for the current window is
transmitted as a short, unambiguous code before the window closes. The opponent's pick
is received at the same time results are revealed. Neither player sees the opponent's
prediction before committing their own.

**The state each client maintains locally:**

Because only drafts and predictions travel over the wire, each client must be able to
reconstruct full game state from those two inputs plus the shared sports data. Concretely,
each client knows:

- Its own drafted athletes
- The opponent's drafted athletes (received at draft time)
- The live event data from the sports feed (same for both clients)
- Its own prediction for each window
- The opponent's prediction for each window (received at resolution time)

From those five inputs, every scorable outcome, every card interaction, every derived game
state must be fully deterministic. If the designer creates a mechanic that requires
information beyond those five inputs — for example, a hidden resource that one player
accumulates without the other knowing — that mechanic cannot be implemented in the
current architecture without extending what gets transmitted.

**What this means for prediction design:** A prediction must be representable as a single
short code that both clients can evaluate independently against the same incoming event
data and reach the same conclusion. The categories of prediction are for the designer to
define. They can be as simple as "event type only" or as structured as a tiered numerical
estimate — as long as the evaluation rule is unambiguous and both clients run it identically.

---

### Constraint 4: Events Are What the API Reports

The game scores based on events that the official sports data feed actually records. For
NHL hockey those events include goals, shots on goal, missed shots, blocked shots,
penalties, hits, giveaways, takeaways, faceoffs, and stoppages. For FIFA World Cup soccer
those events include goals (including own goals and penalty goals), yellow cards, red cards,
substitutions, corners, and VAR reviews.

The game cannot score based on events the feed does not track. It cannot score based on
things that happen in the real game that the API ignores. It cannot score based on
statistical accumulations that are only visible at the end of a period.

**What this means for design:**

The designer's scoring vocabulary is bounded by the event vocabulary of the two feeds.
A mechanic that cannot be evaluated by checking an incoming event object against a rule
cannot exist in v1. Treat the event list as a menu of scoring ingredients.

Events vary significantly in frequency. Hits in NHL happen constantly. Goals in FIFA can
be separated by 90 minutes of play. A well-designed prediction and scoring system will
account for frequency — either by assigning different values to rare versus common events,
or by designing prediction types that are naturally calibrated to event likelihood.

---

### Constraint 5: The Draft Locks Your Hand Before the Game

At the start of each session, both players go through a draft. They select athletes from
the day's available pool. Once the draft is complete, those selections are locked for the
entire session. The draft happens once. Whatever mechanism the designer creates for using
cards during the game must work with the hand each player locked in at the start.

**What this means for design:**

The draft is a consequential opening phase. The designer should ensure it feels like a
real decision rather than a formality. The pool is ordered using a random seed shared
between both clients, so both players see the same pool in the same arrangement. The draft
UI shows real athlete names, positions, and teams as a minimum. Whether it shows anything
beyond that — historical context, flavour, card powers — is a design decision.

---

### Constraint 6: One Real Game, But Players Need Not Be Simultaneous

A session is tied to one live sports event. That event happens at a fixed real-world time
and produces a fixed, historical record of events once it is over. That record does not
change. A goal scored in the 34th minute was scored in the 34th minute forever.

This creates a possibility the designer should consider seriously: players do not have
to engage with the game at the same time, or even with each other directly.

In the synchronous form, both players are live together — drafting, predicting, and
resolving in real time as the game unfolds. This is the head-to-head experience described
throughout this document.

In the asynchronous form, any number of players engage with the same real game
independently — each running their own session against the same event record, submitting
their own draft and predictions either live or after the fact. Their scores are computed
against the same ground truth. At the end, all scores are posted to a shared leaderboard.
The competition is not head-to-head in real time; it is comparative — how did your
predictions stack up against everyone else who played that game?

The asynchronous form removes the need for two players to coordinate a shared session.
It scales to any number of participants. It allows someone to play a game they watched
live, or to play a completed game the next morning. It turns every real sports event into
a puzzle that anyone can attempt, with a community leaderboard as the social layer.

Both forms are architecturally compatible with what is already designed. The PHP relay
handles live synchronous state. A leaderboard endpoint on the same server handles
asynchronous score submission. The designer does not have to choose one — the game could
support both simultaneously, with live sessions feeding into the same leaderboard as
solo runs.

What the designer must decide is which form is primary, how the two relate to each other,
and whether the card and prediction mechanics work equally well in both contexts or need
to be adapted.

---

## The Flexible Space

Within the hard constraints above, the following are genuinely open. The designer should
treat these as creative territory, not settled decisions. The suggestions below are starting
points, not recommendations.

---

### What Do Cards Actually Do?

The constraint says athletes form a hand of cards. It does not say what a card does.
Some directions worth considering:

Cards might be purely passive — an athlete accumulates points automatically when they
appear in an event, and holding their card means those points come to you. Strategy is
entirely about predicting which athletes will be active.

Cards might have active powers — played during a window to modify predictions, protect
against losses, multiply a correct call, or interact with the opponent's hand in some way.
A played card might be consumed, returned to hand, or cycled.

Cards might form a deck that is drawn from each window, so you can only act on athletes
you happen to hold at that moment. Deck management becomes a mechanic across the session.

Cards might carry conditional triggers — a defenseman card that scores differently based
on what kind of event fires, or a forward card that interacts with the opponent's goalie
card. The athlete matters, and so does the situation they appear in.

Cards might encode numerical values — strength ratings, probability weights, modifiers —
that feed directly into prediction mathematics rather than acting as discrete objects with
discrete powers.

These are possible directions, not an exhaustive list. The designer should pick a clear
mechanic, commit to it, and build the prediction system to work with it. The card mechanic
and the prediction mechanic should feel designed for each other.

---

### What Shape Can Predictions Take?

Predictions must be short codes that both clients evaluate identically. Within that
constraint, the mathematical and structural shape of a prediction is entirely open.

A prediction could be a simple categorical choice — pick one event type from a list,
right or wrong. It could be an ordered ranking across multiple event types. It could be
a numerical estimate — how many of a given event will occur in the next window — scored
by proximity to the actual count. It could be a conditional: "if event A occurs, then
event B will follow." It could be a confidence-weighted bet where the player stakes some
resource on the strength of their conviction. It could be a card play that implicitly
constitutes a prediction.

The prediction system can be identical for both players, or asymmetric — one player
predicts one type of thing, the other predicts another, and the game aggregates both into
a shared or competing outcome.

The designer should define what a prediction is and what correct and incorrect mean before
defining anything else. Everything downstream — card interactions, scoring, session arc —
depends on that definition.

---

### Cooperative, Competitive, Solo, or Crowd?

The architecture supports both players' predictions being visible to both clients in a
live session. A leaderboard server can collect scores from any number of independent runs
against the same game. What the game does with all of that is open.

The game could be purely competitive and live — each player is trying to outscore the
other in real time, predictions are independent, and the relationship between them is
purely adversarial.

The game could be cooperative and live — both players are trying to collectively achieve
something against the unpredictable real game as the shared opposition. A streak of
correct predictions, a target score, surviving a difficult stretch of play.

The game could be asymmetric — one player is in an advantaged position and the other is
trying to overcome it, or both players have different roles with different prediction types
and different scoring logic that only makes sense when combined.

The game could be something stranger — the two predictions combine into a joint outcome,
and both players succeed or fail together based on a result that neither fully controlled.

The game could be primarily solo — each player runs their own session against the live or
completed game, submitting a final score to a shared leaderboard. The competition is
asynchronous and communal. There is no opponent in the room; the opponent is everyone
else who played that game, compared after the fact.

The game could support all of these simultaneously — a live head-to-head session that also
feeds a public leaderboard, so playing with a friend and playing alone both contribute to
the same community record.

The designer should make a clear choice about which mode is primary and ensure the draft,
prediction, and card mechanics work in that mode. If secondary modes are supported, the
designer should specify what changes and what stays the same.

---

### How Do the Two Sports Relate?

The game works for both NHL hockey and FIFA World Cup soccer. A session is played on one
sport, chosen at the start. The event vocabularies are different. The frequency of events
is very different. The emotional character of each sport is different.

The designer should decide how the game relates to these two sports:

The game could feel identical in both — same prediction menu, same card powers, same
scoring structure, same session arc. One design, two data sources.

The game could adapt to each sport — different prediction categories, different point
weights, different card behaviors, tuned to the rhythm and character of each. NHL has
constant action and frequent events; FIFA has long stretches of tension punctuated by
rare high-drama moments. A well-tuned adaptation would feel like a different experience
in each sport even though the underlying architecture is the same.

The game could integrate both sports simultaneously — if two games are live at the same
time (an NHL game and a World Cup match on the same evening), the prediction system draws
from both feeds at once. Players might draft athletes across both sports and predict events
from either. This is a more complex design but is architecturally possible.

---

### What Does the Session Arc Feel Like?

A real NHL game is roughly two and a half hours. A FIFA match is roughly two hours. That
is a lot of two-minute windows. The designer should think about how the session builds and
resolves over that time.

Does the game have phases — a draft phase, a mid-game phase, a late-game phase — with
different mechanics or stakes in each? Does the value of a correct prediction increase as
the real game clock runs down? Is there a natural climax built into the structure, or does
the game rely on the real sports event to provide it?

Early windows might establish position. Middle windows might allow cards or powers to
interact. Final windows might be the moment everything that was built over the session
resolves. Or the arc could be flat — every window the same, with variance coming entirely
from the real game. Both are valid choices.

---

## Summary of Constraints for Reference

| Constraint | What It Fixes | What It Leaves Open |
|---|---|---|
| 120-second window; predict before, resolve after | Round duration and blind-prediction timing | What happens inside each round |
| Real athlete roster | Card pool source | Card design, powers, art, flavour, duplicates allowed |
| Drafts and predictions are the only transmitted state | What crosses the wire | All derived scoring, card resolution, game state |
| API event vocabulary | What events can be scored | Point values, prediction categories, rarity weighting |
| Draft locks hand before game | Players commit before first window | Draft format, hand size, how cards are used during game |
| Session tied to one real game | Game event record is fixed and shared | Live head-to-head, async solo, or leaderboard crowd |
| Score is computable from shared inputs | Anyone who plays the same game gets a comparable score | Whether a leaderboard exists and what it shows |
| Two sports available | NHL and FIFA are both supported | Whether they feel identical, adapted, or integrated |

---

*This document is a brief, not a spec. It describes the walls of the room.
The furniture — the win condition, the prediction types, the card powers, whether the
room holds two players or a crowd — is yours to design.*
