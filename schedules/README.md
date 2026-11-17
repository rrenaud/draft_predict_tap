# Alternative schedules

Twenty players, ten rounds. Each round has 2 drafters, 8 gamblers and 10 tappers, and every player drafts once,
gambles 4 times and taps 5 times. Each JSON file has the round-by-round roles (`rounds`), a per-player view
(`players`: roles as a letter string, tapping rounds, longest wait, late-round value) and the `metrics` below.
Regenerate with `python3 generate_schedules.py` (the short-waits variant needs `pip install ortools`).

## Comparison

| Schedule | Co-occurrence (lower is better, optimum 1150) | Times a pair taps together | Longest wait | Late value range (mean 3.00) | Late imbalance |
|---|---|---|---|---|---|
| [balanced](balanced.json) (default) | 1154 | 1–4 (one pair at 4) | 2 | 2.55–3.30 | 356 |
| [pairing-optimal](pairing-optimal.json) | **1150, proven optimal** | 1–3 | 2 | 2.50–3.50 | 652 |
| [late-fair](late-fair.json) | 1176 | 1–4 (six pairs at 4) | 2 | **2.80–3.15** | **102** |
| [two-cabs](two-cabs.json) (2 cabinets) | 1250, proven optimal for parallel play | 0–4 | **0** | **3.00–3.00** | **0** |
| [short-waits](short-waits.json) | 1450, proven optimal for a 1-round limit | 0–5 | **1** | 2.50–3.50 | 1356 |
| [kqaf-original](kqaf-original.json) (baseline) | 1192 | 0–5 | 4 | 2.65–3.45 | 546 |

What the columns mean:

- **Co-occurrence**: the sum over all 190 pairs of players of (rounds they tap together)². The total is fixed,
  so lower means more even mixing. 1150 is a proven lower bound for any schedule (see `main.py`). Two players
  are off the cabinet together exactly as often as they tap together, so this balances sitting out as well.
- **Longest wait**: the most rounds anyone sits out between two of their tapping rounds.
- **Late value**: each round is worth 0.5 to tap, except round 7 (0.55), 8 (0.65), 9 (0.8) and 10 (1.0).
  A player's late value is the total over the rounds they tap. **Late imbalance** is the sum over players of
  (value − 3.0)², in units of 0.05.

## Other event sizes (14 to 26 players)

There are players / 2 rounds (7 to 13), each with 2 drafters, 10 tappers per cab and everyone else gambling,
so every player still taps exactly 5 times and drafts once, and gambles (players − 12) / 2 times (1 to 7).
Below 20 players only one cab is possible, since two cabs need 20 tappers at once. With two cabs, rounds are paired into time slots with disjoint tappers, and with an odd number of
rounds the final round is played alone on one cab. Players 21 to 26 are placeholder names. Each file's
`description` and `critique` are written from its own numbers.

| Schedule | Players | Cabs | Rounds | Co-occurrence / proven lower bound | Times a pair taps together | Longest wait | Late value range |
|---|---|---|---|---|---|---|---|
| [balanced-14](balanced-14.json) | 14 | 1 | 7 | 1113 / 1113 (optimal) | 3–4 | 2 | 2.95–3.50 (mean 3.21) |
| [balanced-16](balanced-16.json) | 16 | 1 | 8 | 1120 / 1120 (optimal) | 2–4 | 2 | 2.55–3.35 (mean 3.12) |
| [balanced-18](balanced-18.json) | 18 | 1 | 9 | 1125 / 1125 (optimal) | 1–4 | 2 | 2.55–3.50 (mean 3.06) |
| [balanced-22](balanced-22.json) | 22 | 1 | 11 | 1159 / 1155 | 1–3 | 3 | 2.50–3.45 (mean 2.95) |
| [two-cabs-22](two-cabs-22.json) | 22 | 2 | 11 | 1255 / 1255 (optimal) | 0–4 | 1 | 2.75–3.25 (mean 2.95) |
| [balanced-24](balanced-24.json) | 24 | 1 | 12 | 1188 / 1188 (optimal) | 1–3 | 3 | 2.50–3.35 (mean 2.92) |
| [two-cabs-24](two-cabs-24.json) | 24 | 2 | 12 | 1260 / 1260 (optimal) | 0–4 | 1 | 2.60–3.00 (mean 2.92) |
| [balanced-26](balanced-26.json) | 26 | 1 | 13 | 1209 / 1209 (optimal) | 0–3 | 3 | 2.50–3.45 (mean 2.88) |
| [two-cabs-26](two-cabs-26.json) | 26 | 2 | 13 | 1281 / 1281 (optimal) | 0–3 | 2 | 2.52–3.25 (mean 2.88) |

What changes with fewer players: everyone taps 5 of only 7–9 rounds, so the same people play together much
more often (3.5 games per pair on average at 14 players, against 2.4 at 20), waits stay at 2 or less, and only
2–6 people gamble each round. All three small sizes meet the proven lower bound exactly; at 14 players every
pair taps together 3 or 4 times.

What changes with more players:

- **Waits.** On one cab everyone sits out more rounds (8 of 13 with 26 players), so the wait limit is 3 rounds
  instead of 2. Holding it at 2 costs real balance: 26 players would get 1287 instead of the optimal 1209.
- **Two cabs no longer cover everyone.** With more than 20 players, the extras sit out tapping in each slot
  and gamble on both games, so waits return (at most 1–2 slots) and late rounds are no longer shared
  automatically. Rounds played at the same time count as equally late.
- **Mixing.** The proven lower bound is met exactly in five of six cases (balanced-22 is 4 above it). Two cabs
  still cost mixing: 100 points over one cab at 22 players (as at 20), 72 at 24 and 26. Every two-cab schedule
  has a few pairs that never tap together (2–10); on one cab that first happens at 26 players (3 pairs).
- **Late-round balance.** The late-round weight keeps its 20-player setting and makes little difference at these
  sizes; values span about 0.5–0.95 around the mean on one cab and 0.4–0.75 on two.

## The schedules

### balanced (recommended)

The `main.py` default. Waits are capped at 2 rounds, everyone's late value is within 2.55–3.30, and
co-occurrence is 1154, just off the 1150 optimum.

*Critique:* it gives up the provable co-occurrence optimum. One pair taps together 4 times and one more pair
only once, which is barely noticeable at the event and buys a clearly fairer split of the late rounds. Late
balance and gambling spread are good, but neither is proven optimal.

### pairing-optimal

Ignores late rounds. Co-occurrence is provably optimal: every pair taps together 1–3 times. Waits are capped
at 2.

*Critique:* the best possible mixing, with a proof, but who plays the finale is left to chance. One player
misses rounds 7–10 entirely while another plays all four. Even with late-round weighting turned on, this
co-occurrence score can't reach a late imbalance below 476: at 1150 every two rounds must share 4 or 5
tappers, which forces round 7–10 tapper sets to overlap.

### late-fair

Weights late-round fairness heavily. Everyone's late value is within about 0.2 of the mean.

*Critique:* the fairest finale. The cost is mixing: six pairs tap together 4 times and 27 pairs only once, so
some players see noticeably more of each other. Worth it if the last rounds are the main event. Perfect late
balance isn't on the table: it would require half the players to tap rounds 7, 8 and 9 together.

### two-cabs

Two cabinets. Rounds run in simultaneous pairs (1+2, 3+4, … 9+10) with disjoint tappers, so every player taps
exactly once per time slot. Each round's drafters and gamblers are the other round's tappers, and both drafts
and predictions happen in parallel at the start of the slot. The event takes half as long. In the JSON, each
round has a `time_slot` and a `cab`.

*Critique:* no waiting at all, and late rounds are shared perfectly evenly by construction (everyone plays the
final slot). Mixing is coarser: each slot splits the room into two halves, so the two rounds in a slot share
no tappers and the co-occurrence floor rises to 1250. That floor is met exactly when every two slots are
"orthogonal" (each combination of cabs holds exactly 5 players), as in 5 columns of a Hadamard matrix of order
20. Some pairs must be extreme: the 32 possible cab patterns form 16 complementary pairs, so with 20 players
some two players are together in every slot or in none. At 1250 the fewest such pairs is 5 (proven with
CP-SAT), and this schedule reaches it: 5 pairs never tap together, and every other pair taps together 1–4 times.
Gambling is less even too (15 pairs never gamble together), since you only ever gamble on the other half of the room.

### short-waits

Nobody sits out more than one round between games. Solved exactly with CP-SAT (`exact_model.py`), since the
annealer struggles with a limit this tight.

*Critique:* not recommended. A one-round limit makes 1450 the best possible co-occurrence (proven, against 1150
without it). Players fall into near-fixed cohorts: 20 pairs never tap together while 10 pairs tap together in
all 5 of their rounds. Late values are also the most uneven of all the variants. Included to show what that
constraint costs.

### kqaf-original (baseline)

The algorithm used at the first DPT tournament at KQAF (commit `3e9bc87`), run with `random.seed(0)`: a
rotating template plus 10,000 random role swaps that keep role counts fixed.

*Critique:* role counts are right, but nothing balances who plays with whom, waiting or the finale. One pair
never taps together and another taps together in all 5 rounds; 12 pairs are at 4. One player waits 4 rounds
between games and five wait 3. Useful only as a comparison point.
