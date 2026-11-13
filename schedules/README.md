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
