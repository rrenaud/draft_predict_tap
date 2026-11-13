# Exact (operations research) model for the tapping schedule, using Google OR-Tools CP-SAT.
#
#     pip install ortools
#     python3 exact_model.py --max-wait 2 --seconds 600
#
# main.py finds schedules quickly with simulated annealing and certifies them against an analytic lower bound.
# This model answers the questions that annealing can't: what is the best possible co-occurrence under a given
# wait limit, with a proof.
#
# Formulation. Players are interchangeable, so instead of assigning players to rounds (which leaves 20!
# equivalent relabelings for the solver to wade through) we choose a multiset of tapping *patterns*: a pattern
# is the set of K rounds a player taps in. Wait limits are then just a filter on which patterns are allowed.
#   x_i in {0,1}      pattern copy i is used (each pattern may be used up to twice; copy 2 only if copy 1)
#   sum_i x_i = P                       one pattern per player
#   sum_{i: r in pattern i} x_i = T     T tappers in every round
#   y_ij >= x_i + x_j - 1               both copies used, i.e. some pair of players has these patterns
#   minimize sum_ij |pattern_i & pattern_j|^2 * y_ij
# The objective is exactly sum over player pairs of (rounds tapped together)^2, the quantity main.py minimizes.
# The trace-identity lower bound from main.py is added as a constraint, which helps the solver close the gap.
#
# Results with 20 players, 10 rounds, 10 tappers:
#   --max-wait 1: optimum 1450, proven in a few seconds (much worse balance than 1150).
#   --max-wait 2: optimum 1150, proven in about 4 minutes on 4 cores, so capping waits at 2 costs nothing.

import argparse
from itertools import combinations

from ortools.sat.python import cp_model

import main as dpt


def solve(max_wait: int, seconds: float, workers: int):
    R, P, K, T = dpt.NUM_ROUNDS, dpt.NUM_PLAYERS, dpt.TAPS_PER_PLAYER, dpt.ROLE_SIZES[dpt.Role.TAPPER]
    patterns = [frozenset(s) for s in combinations(range(R), K)
                if max(b - a - 1 for a, b in zip(s, s[1:])) <= max_wait]
    items = [s for s in patterns for _ in range(2)]

    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x{i}") for i in range(len(items))]
    for i in range(0, len(items), 2):
        model.Add(x[i + 1] <= x[i])
    model.Add(sum(x) == P)
    for r in range(R):
        model.Add(sum(x[i] for i, s in enumerate(items) if r in s) == T)

    terms = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            weight = len(items[i] & items[j]) ** 2
            if weight:
                y = model.NewBoolVar(f"y{i}_{j}")
                model.Add(y >= x[i] + x[j] - 1)
                terms.append(weight * y)
    objective = sum(terms)
    model.Add(objective >= dpt.tap_lower_bound())
    model.Minimize(objective)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = workers
    status = solver.Solve(model)

    print(f"max wait {max_wait}: {len(patterns)} allowed patterns, status {solver.StatusName(status)}, "
          f"best {solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None}, "
          f"lower bound {solver.BestObjectiveBound():.0f}, {solver.WallTime():.0f}s")
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for i, s in enumerate(items):
            if solver.Value(x[i]):
                print(''.join('X' if r in s else '.' for r in range(R)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--max-wait', type=int, default=dpt.MAX_WAIT)
    parser.add_argument('--seconds', type=float, default=600)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    solve(args.max_wait, args.seconds, args.workers)
