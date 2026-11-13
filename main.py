# Generate a round -> roles sheet for the play draft gamble, with player co-occurrence balanced as evenly
# as possible.
#
# Every round has ROLE_SIZES[role] players in each role. Every player gets the same number of rounds in each
# role (each player drafts once, gambles 4 times and taps 5 times with the default sizes).
#
# Primary objective: for every pair of players, the number of rounds they tap (play) together should be as
# even as possible. We minimize sum over pairs of together(p, q)^2. Because the total number of tapping pairs
# is fixed, this is the same as minimizing the variance of the pair counts.
#
# Note that "tap together" and "sit out together" are the same number: if p and q tap together L times, they
# are both off the cabinet R - k - k + L times. So balancing one balances the other.
#
# Proving optimality. Let M be the players x rounds 0/1 tapping matrix. Pair counts are L = M M^T and round
# overlaps are U = M^T M. trace(L^2) = trace(U^2), which gives
#     sum_{p<q} L_pq^2 = (R*T^2 - P*k^2) / 2 + sum_{a<b} U_ab^2
# where T = tappers per round and k = taps per player. Both sums have a fixed total, so each is bounded below
# by spreading its total as evenly as possible across integers. The larger of the two bounds is a lower bound
# on the objective; when the search reaches it, the schedule is provably optimal.
#
# With 20 players and 10 rounds: the naive bound (every pair together 2 or 3 times) is 1110, but the round
# overlap bound is 1150, so the "all 2s and 3s" schedule does not exist. With LATE_WEIGHT = 0 the search
# reaches 1150 with every pair tapping together 1-3 times (20 pairs once, 80 twice, 90 three times). The sum of
# squares has many tied optima, so a tiebreak term picks one with no pair at 0 and none above 3; since some
# pair must fall outside {2, 3}, a range of 1-3 is as tight as possible.
#
# Late-round balance at the 1150 optimum: every two rounds must then share 4 or 5 tappers, and a small integer
# program over which of rounds 7-10 each player taps shows the late imbalance is at least 476, with values
# spread at least 2.55-3.30. The default LATE_WEIGHT accepts 1152 to get imbalance 356 within 2.55-3.30.
#
# Wait times: nobody sits out more than MAX_WAIT = 2 rounds between two rounds they tap, and shorter waits are
# preferred as a soft tiebreak. exact_model.py (CP-SAT) proves that a limit of 2 still allows the 1150 optimum,
# while a limit of 1 cannot do better than 1450.
#
# Late rounds: ROUND_VALUES makes later rounds worth more, and each player's total value of rounds tapped is
# balanced too. This trades off slightly against co-occurrence; see LATE_WEIGHT.
#
# Secondary objective: once tapping is fixed, choose drafters (each player drafts exactly once, in a round
# they are not tapping) to balance how often pairs of players gamble in the same round.

import math
import random
import sys
from enum import IntEnum
from typing import Dict, List, Tuple


class Role(IntEnum):
    DRAFTER = 0
    GAMBLER = 1
    TAPPER = 2


ROLE_SIZES = {Role.DRAFTER: 2, Role.GAMBLER: 8, Role.TAPPER: 10}
NUM_PLAYERS = sum(ROLE_SIZES.values())
NUM_ROUNDS = 10

for _role, _size in ROLE_SIZES.items():
    assert (_size * NUM_ROUNDS) % NUM_PLAYERS == 0, f"{_role.name} slots don't divide evenly among players"

TAPS_PER_PLAYER = ROLE_SIZES[Role.TAPPER] * NUM_ROUNDS // NUM_PLAYERS
DRAFTS_PER_PLAYER = ROLE_SIZES[Role.DRAFTER] * NUM_ROUNDS // NUM_PLAYERS

players = ["Rob", "Nick M", "Brian", "Ryan P", "Woody", "Wyatt", "Mario", "Tyler", "John Ryan", "Jimmy J Leong",
           "TayTay", "Sam B", "TJ", "Dan", "Marian", "Alec", "Daph", "Keith", "Joyce", "Coppola"]
assert len(players) == NUM_PLAYERS

Schedule = List[List[Role]]  # schedule[player][round]


def even_split_sum_of_squares(total: int, bins: int) -> int:
    """Smallest possible sum of x_i^2 over `bins` nonnegative integers summing to `total`."""
    q, r = divmod(total, bins)
    return r * (q + 1) ** 2 + (bins - r) * q ** 2


def tap_lower_bound() -> int:
    P, R, T, k = NUM_PLAYERS, NUM_ROUNDS, ROLE_SIZES[Role.TAPPER], TAPS_PER_PLAYER
    pair_bound = even_split_sum_of_squares(R * math.comb(T, 2), math.comb(P, 2))
    round_bound = (R * T * T - P * k * k) // 2 + even_split_sum_of_squares(P * math.comb(k, 2), math.comb(R, 2))
    return max(pair_bound, round_bound)


def pair_counts(sets_per_round: List[List[int]]) -> List[List[int]]:
    counts = [[0] * NUM_PLAYERS for _ in range(NUM_PLAYERS)]
    for members in sets_per_round:
        for i, p in enumerate(members):
            for q in members[i + 1:]:
                counts[p][q] += 1
                counts[q][p] += 1
    return counts


def pair_sum_of_squares(counts: List[List[int]]) -> int:
    return sum(counts[p][q] ** 2 for p in range(NUM_PLAYERS) for q in range(p + 1, NUM_PLAYERS))


MEAN_TOGETHER = NUM_ROUNDS * math.comb(ROLE_SIZES[Role.TAPPER], 2) / math.comb(NUM_PLAYERS, 2)
MAX_TOGETHER = math.ceil(MEAN_TOGETHER)


def tap_weight(x: int) -> int:
    """Annealing cost for one pair tapping together x times.

    Dominated by x^2 (the provable objective). Among the many schedules tied on sum of squares, the quartic
    term prefers counts near the mean (no 0s), and the last term prefers never exceeding ceil(mean).
    """
    return 64 * x * x + (2 * x - 2 * MEAN_TOGETHER) ** 4 + (50 if x > MAX_TOGETHER else 0)


# Longest allowed wait: rounds a player sits out between two rounds they tap. With the default sizes, 2 is the
# smallest limit that still allows the optimal co-occurrence (1150, proven with exact_model.py); a limit of 1
# forces the co-occurrence optimum up to 1450, with some pairs tapping together in all 5 of their rounds.
MAX_WAIT = 2
# Soft cost per gap of g rounds: prefer short waits but never at the expense of co-occurrence balance.
SHORT_WAIT_COST = 20


def waits(row: List[int]) -> List[int]:
    """Rounds sat out between consecutive tapping rounds, for one player's tapping row."""
    rounds = [r for r, t in enumerate(row) if t]
    return [b - a - 1 for a, b in zip(rounds, rounds[1:])]


# How much tapping in each round is worth; late rounds are more fun to play. Every player taps the same number
# of rounds, so only the extra value of late rounds matters, and we balance each player's total.
ROUND_VALUES = [0.5] * (NUM_ROUNDS - 4) + [0.55, 0.65, 0.8, 1.0]
MEAN_LATE_VALUE = sum(ROUND_VALUES) * ROLE_SIZES[Role.TAPPER] / NUM_PLAYERS
# Late value is measured in units of 0.05 (the smallest step between round values) for the cost below.
LATE_UNIT = 0.05
# Cost per player of (late value - mean)^2, in units of LATE_UNIT. Late balance competes with co-occurrence:
# perfect late balance would need half the players to tap rounds 7, 8 and 9 together, and at the proven
# co-occurrence optimum (1150) the late imbalance is at least 476 (in LATE_UNIT^2). With weight 2 the search
# gives up a single step of co-occurrence (1152, two pairs together 4 times) and gets late values within
# 2.55-3.30 around a mean of 3.0, with imbalance 356. Set to 0 to ignore late rounds.
LATE_WEIGHT = 2
# Late values further than this below or above the mean are penalized heavily (default window 2.55-3.30).
LATE_TOLERANCE_BELOW = 0.45
LATE_TOLERANCE_ABOVE = 0.30


def late_value(row: List[int]) -> float:
    return sum(v for v, t in zip(ROUND_VALUES, row) if t)


def player_cost(row: List[int]) -> float:
    """Per-player annealing cost: wait times plus late-round balance."""
    cost = sum(5000 * (g - MAX_WAIT) if g > MAX_WAIT else SHORT_WAIT_COST * max(0, g - 1) ** 2
               for g in waits(row))
    if LATE_WEIGHT:
        deviation = (late_value(row) - MEAN_LATE_VALUE) / LATE_UNIT
        cost += LATE_WEIGHT * deviation ** 2
        below, above = LATE_TOLERANCE_BELOW / LATE_UNIT + 1e-9, LATE_TOLERANCE_ABOVE / LATE_UNIT + 1e-9
        if not -below <= deviation <= above:
            cost += 3000
    return cost


def tap_quality(tap: List[List[int]]) -> Tuple[int, float]:
    """Score to compare restarts, lower is better: (rounds of wait over the limit, total annealing cost)."""
    counts = pair_counts(tappers_by_round(tap))
    longest = max(max(waits(row)) for row in tap)
    total = (sum(tap_weight(counts[p][q]) for p in range(NUM_PLAYERS) for q in range(p + 1, NUM_PLAYERS)) +
             sum(player_cost(row) for row in tap))
    return max(0, longest - MAX_WAIT), total


def optimize_tappers(rng: random.Random, iterations: int) -> List[List[int]]:
    """Simulated annealing over the players x rounds tapping matrix.

    A move takes players p, q and rounds a, b where p taps in a but not b and q taps in b but not a, and swaps
    them. This keeps both row sums (taps per player) and column sums (tappers per round) fixed. The cost is
    tap_weight over pairs plus wait_cost over players.
    """
    P, R = NUM_PLAYERS, NUM_ROUNDS
    stride = P / R
    tap = [[1 if (p - int(r * stride)) % P < ROLE_SIZES[Role.TAPPER] else 0 for r in range(R)] for p in range(P)]
    together = [[sum(tap[p][r] * tap[q][r] for r in range(R)) if p != q else 0 for q in range(P)]
                for p in range(P)]
    player_costs = [player_cost(row) for row in tap]
    cost = sum(tap_weight(together[p][q]) for p in range(P) for q in range(p + 1, P)) + sum(player_costs)
    best_cost, best_tap = cost, [row[:] for row in tap]
    temperature = 50.0
    for _ in range(iterations):
        p, q = rng.sample(range(P), 2)
        a, b = rng.sample(range(R), 2)
        if not (tap[p][a] and not tap[p][b] and not tap[q][a] and tap[q][b]):
            continue
        # p moves a -> b and q moves b -> a. together[p][q] is unchanged; for every other player x,
        # together[p][x] changes by tap[x][b] - tap[x][a] and together[q][x] by the opposite.
        tap[p][a], tap[p][b], tap[q][a], tap[q][b] = 0, 1, 1, 0
        cost_p, cost_q = player_cost(tap[p]), player_cost(tap[q])
        delta = cost_p + cost_q - player_costs[p] - player_costs[q]
        changes = []
        for x in range(P):
            if x == p or x == q:
                continue
            d = tap[x][b] - tap[x][a]
            if d:
                tp, tq = together[p][x], together[q][x]
                delta += (tap_weight(tp + d) - tap_weight(tp) +
                          tap_weight(tq - d) - tap_weight(tq))
                changes.append((x, d))
        if delta <= 0 or rng.random() < math.exp(-delta / temperature):
            for x, d in changes:
                together[p][x] += d
                together[x][p] += d
                together[q][x] -= d
                together[x][q] -= d
            player_costs[p], player_costs[q] = cost_p, cost_q
            cost += delta
            if cost < best_cost:
                best_cost, best_tap = cost, [row[:] for row in tap]
        else:
            tap[p][a], tap[p][b], tap[q][a], tap[q][b] = 1, 0, 0, 1
        temperature = max(1.0, temperature * 0.99999)
    return best_tap


def initial_drafters(tap: List[List[int]]) -> List[List[int]]:
    """Assign each player DRAFTS_PER_PLAYER rounds they don't tap in, with ROLE_SIZES[DRAFTER] per round.

    Bipartite b-matching via augmenting paths; it always exists because the off-cabinet graph is regular.
    """
    P, R, D = NUM_PLAYERS, NUM_ROUNDS, ROLE_SIZES[Role.DRAFTER]
    slots = [(p, i) for p in range(P) for i in range(DRAFTS_PER_PLAYER)]
    round_of_slot: Dict[Tuple[int, int], int] = {}
    slots_in_round: List[List[Tuple[int, int]]] = [[] for _ in range(R)]

    def augment(slot, seen) -> bool:
        p = slot[0]
        for r in range(R):
            if tap[p][r] or r in seen or any(s[0] == p for s in slots_in_round[r]):
                continue
            seen.add(r)
            if len(slots_in_round[r]) < D:
                slots_in_round[r].append(slot)
                round_of_slot[slot] = r
                return True
            for other in slots_in_round[r]:
                if augment(other, seen):
                    slots_in_round[r].remove(other)
                    slots_in_round[r].append(slot)
                    round_of_slot[slot] = r
                    return True
        return False

    for slot in slots:
        assert augment(slot, set()), "no valid drafter assignment"
    return [[s[0] for s in slots_in_round[r]] for r in range(R)]


def optimize_drafters(rng: random.Random, tap: List[List[int]], iterations: int) -> List[List[int]]:
    """Anneal drafter choice to balance how often pairs gamble in the same round."""
    P, R = NUM_PLAYERS, NUM_ROUNDS
    drafters = initial_drafters(tap)

    def gamblers(r):
        return [p for p in range(P) if not tap[p][r] and p not in drafters[r]]

    def cost_of(dr):
        nonlocal drafters
        saved, drafters = drafters, dr
        c = pair_sum_of_squares(pair_counts([gamblers(r) for r in range(R)]))
        drafters = saved
        return c

    cost = cost_of(drafters)
    temperature = 2.0
    for _ in range(iterations):
        # Swap: drafter p in round a and drafter q in round b trade rounds, if both are off-cabinet there.
        a, b = rng.sample(range(R), 2)
        i, j = rng.randrange(len(drafters[a])), rng.randrange(len(drafters[b]))
        p, q = drafters[a][i], drafters[b][j]
        if p == q or tap[p][b] or tap[q][a] or p in drafters[b] or q in drafters[a]:
            continue
        candidate = [row[:] for row in drafters]
        candidate[a][i], candidate[b][j] = q, p
        new_cost = cost_of(candidate)
        if new_cost <= cost or rng.random() < math.exp((cost - new_cost) / temperature):
            drafters, cost = candidate, new_cost
        temperature = max(0.05, temperature * 0.999)
    return drafters


def build_schedule(seed: int = 0, restarts: int = 4) -> Tuple[Schedule, List[List[int]]]:
    rng = random.Random(seed)
    tap = min((optimize_tappers(rng, iterations=1000000) for _ in range(restarts)), key=tap_quality)
    drafters = optimize_drafters(rng, tap, iterations=20000)
    schedule = [[Role.TAPPER if tap[p][r] else Role.GAMBLER for r in range(NUM_ROUNDS)]
                for p in range(NUM_PLAYERS)]
    for r, ds in enumerate(drafters):
        for p in ds:
            schedule[p][r] = Role.DRAFTER
    return schedule, tap


def tappers_by_round(tap: List[List[int]]) -> List[List[int]]:
    return [[p for p in range(NUM_PLAYERS) if tap[p][r]] for r in range(NUM_ROUNDS)]


def histogram(counts: List[List[int]]) -> Dict[int, int]:
    hist: Dict[int, int] = {}
    for p in range(NUM_PLAYERS):
        for q in range(p + 1, NUM_PLAYERS):
            hist[counts[p][q]] = hist.get(counts[p][q], 0) + 1
    return dict(sorted(hist.items()))


def check_schedule(schedule: Schedule):
    for r in range(NUM_ROUNDS):
        for role in Role:
            assert sum(schedule[p][r] == role for p in range(NUM_PLAYERS)) == ROLE_SIZES[role]
    for p in range(NUM_PLAYERS):
        for role in Role:
            assert sum(schedule[p][r] == role for r in range(NUM_ROUNDS)) * NUM_PLAYERS == \
                ROLE_SIZES[role] * NUM_ROUNDS


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    schedule, tap = build_schedule(seed)
    check_schedule(schedule)

    for round_id in range(NUM_ROUNDS):
        names = [players[p] for role in Role for p in range(NUM_PLAYERS) if schedule[p][round_id] == role]
        print(','.join(names) + ',')

    tap_counts = pair_counts(tappers_by_round(tap))
    gamble_counts = pair_counts([[p for p in range(NUM_PLAYERS) if schedule[p][r] == Role.GAMBLER]
                                 for r in range(NUM_ROUNDS)])
    cost, bound = pair_sum_of_squares(tap_counts), tap_lower_bound()
    print(file=sys.stderr)
    print(f"Tapping together, pair count -> number of pairs: {histogram(tap_counts)}", file=sys.stderr)
    note = 'OPTIMAL' if cost == bound else ('above optimum, traded for late-round balance' if LATE_WEIGHT
                                           else 'not proven optimal')
    print(f"  sum of squares {cost}, proven lower bound {bound}: {note}", file=sys.stderr)
    print(f"Gambling together, pair count -> number of pairs: {histogram(gamble_counts)}", file=sys.stderr)
    all_waits = [g for row in tap for g in waits(row)]
    wait_hist = {g: all_waits.count(g) for g in sorted(set(all_waits))}
    print(f"Rounds sat out between taps -> number of gaps: {wait_hist} (limit {MAX_WAIT})", file=sys.stderr)
    late = sorted((round(late_value(tap[p]), 2), players[p]) for p in range(NUM_PLAYERS))
    imbalance = sum(((v - MEAN_LATE_VALUE) / LATE_UNIT) ** 2 for v, _ in late)
    print(f"Late-round value per player (mean {MEAN_LATE_VALUE:.2f}): {late[0][0]:.2f} to {late[-1][0]:.2f}, "
          f"imbalance {imbalance:.0f}", file=sys.stderr)


if __name__ == '__main__':
    main()
