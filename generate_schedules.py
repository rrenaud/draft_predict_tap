# Generate a set of alternative schedules, each with different trade-offs, as JSON files in schedules/.
#
#     python3 generate_schedules.py
#
# Every file holds the round-by-round roles plus the metrics used to compare schedules. The descriptions and
# critiques for each variant live in VARIANTS below and in schedules/README.md.

import json
import os
import random
import subprocess
import sys
from typing import Dict

import main as dpt

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schedules')

VARIANTS = [
    {
        'name': 'balanced',
        'title': 'Balanced (recommended default)',
        'settings': {'MAX_WAIT': 2, 'LATE_WEIGHT': 2, 'LATE_TOLERANCE_BELOW': 0.45, 'LATE_TOLERANCE_ABOVE': 0.30},
        'description': "What main.py produces by default. Waits capped at 2 rounds, late-round value kept within "
                       "2.55-3.30 for everyone, and co-occurrence a hair off the proven optimum (1154 vs 1150).",
        'critique': "Gives up the provable co-occurrence optimum: one pair taps together 4 times and one more "
                    "pair only once. That is barely noticeable at the event, and it buys a clearly fairer split of the late rounds. Late "
                    "balance and the gambling spread are good, not proven optimal.",
    },
    {
        'name': 'pairing-optimal',
        'title': 'Pairing optimal',
        'settings': {'MAX_WAIT': 2, 'LATE_WEIGHT': 0},
        'description': "Ignores late rounds. Co-occurrence is provably optimal (sum of squares 1150): every pair "
                       "taps together 1-3 times. Waits capped at 2 rounds.",
        'critique': "The best possible mixing, with a proof. But who plays the last rounds is left to chance: "
                    "one player misses rounds 7-10 entirely while another plays all four. Even at "
                    "this pairing score the late spread can't be fixed completely: the late imbalance is "
                    "provably at least 476.",
    },
    {
        'name': 'late-fair',
        'title': 'Late-round fair',
        'settings': {'MAX_WAIT': 2, 'LATE_WEIGHT': 30, 'LATE_TOLERANCE_BELOW': 1.0, 'LATE_TOLERANCE_ABOVE': 1.0},
        'description': "Weights late-round fairness heavily. Every player's late value is within about 0.2 of "
                       "the 3.0 mean. Waits capped at 2 rounds.",
        'critique': "The fairest finale. The cost is mixing: more pairs tap together 4 times and more only once, "
                    "so some players see noticeably more of each other. Worth it if the last rounds are the "
                    "main event.",
    },
    {
        'name': 'two-cabs',
        'title': 'Two cabs in parallel',
        'settings': {'NUM_CABS': 2},
        'description': "Two cabinets. Rounds run in simultaneous pairs (1+2, 3+4, ... 9+10) whose tappers are "
                       "disjoint, so every player taps exactly once per time slot. Each round's drafters and "
                       "gamblers are the other round's tappers, drafting and predicting in parallel at the start "
                       "of the slot. The event takes half as long.",
        'critique': "No waiting at all and perfectly even late-round value, by construction. Mixing is coarser: "
                    "every slot splits the room into two fixed halves, which raises the co-occurrence floor to "
                    "1250 (met exactly). By pigeonhole some pairs must be extreme, and the minimum is reached: 5 "
                    "pairs never tap together; every other pair taps together 1-4 times. Gambling is also less "
                    "even, since you only ever gamble on the other half of the room.",
    },
    {
        'name': 'short-waits',
        'title': 'Short waits (max 1 round)',
        'settings': {'MAX_WAIT': 1, 'LATE_WEIGHT': 0},
        'exact': True,
        'description': "Nobody ever sits out more than one round between games. Solved exactly with CP-SAT "
                       "(exact_model.py) because annealing struggles with such a tight limit.",
        'critique': "Not recommended. A one-round wait limit makes 1450 the best possible co-occurrence (proven "
                    "with exact_model.py, against 1150 without it). Players fall into near-fixed cohorts: 20 pairs "
                    "never tap together at all while 10 pairs tap together in all 5 of their rounds. The cohorts also make late-round value "
                    "the most uneven of all the variants. Included to show what that constraint costs.",
    },
]

BASELINE = {
    'name': 'kqaf-original',
    'title': 'Original KQAF script (baseline)',
    'description': "The schedule algorithm used at the first DPT tournament at KQAF (commit 3e9bc87): a rotating "
                   "template plus 10,000 random role swaps that keep role counts fixed, run here with "
                   "random.seed(0).",
    'critique': "Role counts are correct, but nothing balances who plays with whom, how long people wait or "
                "who gets the late rounds. Some pairs tap together far more than others and some players sit "
                "out long stretches. Useful only as a comparison point.",
}


def apply_settings(settings: Dict):
    """Configure the event size first, then override individual knobs the variant names."""
    settings = dict(settings)
    dpt.configure(settings.pop('NUM_PLAYERS', 20), settings.pop('NUM_CABS', 1))
    dpt.LATE_WEIGHT = 2
    for key, value in settings.items():
        setattr(dpt, key, value)


def metrics(schedule: dpt.Schedule) -> Dict:
    P, R = dpt.NUM_PLAYERS, dpt.NUM_ROUNDS
    tap = [[1 if schedule[p][r] == dpt.Role.TAPPER else 0 for r in range(R)] for p in range(P)]
    tap_counts = dpt.pair_counts(dpt.tappers_by_round(tap))
    gamble_counts = dpt.pair_counts([[p for p in range(P) if schedule[p][r] == dpt.Role.GAMBLER]
                                     for r in range(R)])
    all_waits = [g for row in tap for g in dpt.waits(row)]
    late = [round(dpt.late_value(row), 2) for row in tap]
    together = [tap_counts[p][q] for p in range(P) for q in range(p + 1, P)]
    return {
        'tap_together': {
            'sum_of_squares': dpt.pair_sum_of_squares(tap_counts),
            'proven_lower_bound': dpt.tap_lower_bound(),
            'min': min(together),
            'max': max(together),
            'pairs_by_count': {str(k): v for k, v in dpt.histogram(tap_counts).items()},
        },
        'gamble_together': {
            'sum_of_squares': dpt.pair_sum_of_squares(gamble_counts),
            'pairs_by_count': {str(k): v for k, v in dpt.histogram(gamble_counts).items()},
        },
        'waits': {
            'max': max(all_waits),
            'gaps_by_length': {str(g): all_waits.count(g) for g in sorted(set(all_waits))},
        },
        'late_value': {
            'round_values': dpt.ROUND_VALUES,
            'mean': dpt.MEAN_LATE_VALUE,
            'min': min(late),
            'max': max(late),
            'imbalance': round(sum(((v - dpt.MEAN_LATE_VALUE) / dpt.LATE_UNIT) ** 2 for v in late)),
        },
    }


def to_json(variant: Dict, schedule: dpt.Schedule, seed) -> Dict:
    P, R = dpt.NUM_PLAYERS, dpt.NUM_ROUNDS
    names = dpt.players
    rounds = [{
        'round': r + 1,
        'time_slot': dpt.time_slot(r) + 1,
        'cab': r % dpt.NUM_CABS + 1,
        'drafters': [names[p] for p in range(P) if schedule[p][r] == dpt.Role.DRAFTER],
        'gamblers': [names[p] for p in range(P) if schedule[p][r] == dpt.Role.GAMBLER],
        'tappers': [names[p] for p in range(P) if schedule[p][r] == dpt.Role.TAPPER],
    } for r in range(R)]
    by_player = {}
    for p in range(P):
        row = [1 if schedule[p][r] == dpt.Role.TAPPER else 0 for r in range(R)]
        by_player[names[p]] = {
            'roles': ''.join('DGT'[schedule[p][r]] for r in range(R)),
            'tap_rounds': [r + 1 for r in range(R) if row[r]],
            'longest_wait': max(dpt.waits(row)),
            'late_value': round(dpt.late_value(row), 2),
        }
    return {
        'name': variant['name'],
        'title': variant['title'],
        'description': variant['description'],
        'critique': variant['critique'],
        'settings': variant.get('settings', {}),
        'seed': seed,
        'cabs': dpt.NUM_CABS,
        'metrics': metrics(schedule),
        'rounds': rounds,
        'players': by_player,
        'roles_key': 'D = drafter, G = gambler, T = tapper, one letter per round',
    }


def baseline_schedule() -> dpt.Schedule:
    """Run the original KQAF script with a fixed seed and parse its output."""
    source = subprocess.run(['git', 'show', '3e9bc87:main.py'], capture_output=True, text=True, check=True,
                            cwd=os.path.dirname(os.path.abspath(__file__))).stdout
    program = 'import random\nrandom.seed(0)\n' + source
    output = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True, check=True).stdout
    index = {name: p for p, name in enumerate(dpt.players)}
    schedule = [[None] * dpt.NUM_ROUNDS for _ in range(dpt.NUM_PLAYERS)]
    for r, line in enumerate(output.strip().splitlines()):
        names = [n for n in line.split(',') if n]
        roles = ([dpt.Role.DRAFTER] * dpt.ROLE_SIZES[dpt.Role.DRAFTER] +
                 [dpt.Role.GAMBLER] * dpt.ROLE_SIZES[dpt.Role.GAMBLER] +
                 [dpt.Role.TAPPER] * dpt.ROLE_SIZES[dpt.Role.TAPPER])
        for name, role in zip(names, roles):
            schedule[index[name]][r] = role
    return schedule


def exact_schedule(seed: int) -> dpt.Schedule:
    """Solve tapping exactly with CP-SAT (needs ortools), then choose drafters as main.py does."""
    import exact_model
    tap = exact_model.solve(dpt.MAX_WAIT, seconds=300, workers=4)
    assert tap is not None, "CP-SAT found no schedule"
    drafters = dpt.optimize_drafters(random.Random(seed), tap, iterations=20000)
    schedule = [[dpt.Role.TAPPER if tap[p][r] else dpt.Role.GAMBLER for r in range(dpt.NUM_ROUNDS)]
                for p in range(dpt.NUM_PLAYERS)]
    for r, ds in enumerate(drafters):
        for p in ds:
            schedule[p][r] = dpt.Role.DRAFTER
    return schedule


def write(data: Dict):
    path = os.path.join(OUT_DIR, data['name'] + '.json')
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    m = data['metrics']
    print(f"{data['name']:16} co-occurrence {m['tap_together']['sum_of_squares']} "
          f"(pairs {m['tap_together']['min']}-{m['tap_together']['max']}), max wait {m['waits']['max']}, "
          f"late {m['late_value']['min']:.2f}-{m['late_value']['max']:.2f} "
          f"(imbalance {m['late_value']['imbalance']}), gamble sumsq {m['gamble_together']['sum_of_squares']}")


LARGER_EVENTS = [22, 24, 26]


def larger_event_variant(num_players: int, num_cabs: int, schedule: dpt.Schedule) -> Dict:
    """Name, description and critique for a larger event, written from the schedule's own numbers."""
    m = metrics(schedule)
    t, w, l = m['tap_together'], m['waits'], m['late_value']
    rounds, gambles = dpt.NUM_ROUNDS, dpt.ROLE_SIZES[dpt.Role.GAMBLER] * dpt.NUM_ROUNDS // num_players
    optimal = t['sum_of_squares'] == t['proven_lower_bound']
    score = (f"Co-occurrence is {t['sum_of_squares']}, "
             + ("exactly the proven lower bound, so no schedule mixes players more evenly. " if optimal else
                f"{t['sum_of_squares'] - t['proven_lower_bound']} above the proven lower bound of "
                f"{t['proven_lower_bound']}. "))
    extremes = t['pairs_by_count'].get('0', 0)
    never = f" {extremes} pairs never tap together." if extremes else ""
    late = (f" Late-round value ranges {l['min']:.2f}-{l['max']:.2f} around a mean of {l['mean']:.2f} "
            f"(imbalance {l['imbalance']}).")
    if num_cabs == 1:
        variant = {
            'name': f'balanced-{num_players}',
            'title': f'Balanced, {num_players} players',
            'description': f"One cab, {num_players} players, {rounds} rounds of 2 drafters, "
                           f"{dpt.ROLE_SIZES[dpt.Role.GAMBLER]} gamblers and 10 tappers. Everyone taps 5 times, "
                           f"drafts once and gambles {gambles} times.",
            'critique': score + f"Pairs tap together {t['min']}-{t['max']} times.{never} With more players "
                        f"everyone sits out more rounds, so the wait limit is 3 rounds instead of 2 "
                        f"(longest wait here: {w['max']}); a 2-round limit would cost noticeably more "
                        f"co-occurrence balance." + late,
        }
    else:
        solo = " The final round is played alone on one cab." if rounds % 2 else ""
        variant = {
            'name': f'two-cabs-{num_players}',
            'title': f'Two cabs, {num_players} players',
            'description': f"Two cabs, {num_players} players, {rounds} rounds played in parallel pairs with "
                           f"disjoint tappers.{solo} Each round's drafters and gamblers are everyone not "
                           f"tapping it, and nobody drafts both games of a slot. Everyone taps 5 times, drafts "
                           f"once and gambles {gambles} times.",
            'critique': score + f"Pairs tap together {t['min']}-{t['max']} times.{never} With more than 20 "
                        f"players, {num_players - 20} people sit out tapping in each parallel slot and gamble "
                        f"on both games, so waits come back (longest: {w['max']} slot"
                        f"{'s' if w['max'] != 1 else ''}) and late rounds are no longer shared automatically."
                        + late,
        }
    variant['settings'] = {'NUM_PLAYERS': num_players, 'NUM_CABS': num_cabs}
    return variant


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    seed = 0
    for num_players in LARGER_EVENTS:
        for num_cabs in (1, 2):
            apply_settings({'NUM_PLAYERS': num_players, 'NUM_CABS': num_cabs})
            schedule, _ = dpt.build_schedule(seed)
            dpt.check_schedule(schedule)
            write(to_json(larger_event_variant(num_players, num_cabs, schedule), schedule, seed))
    for variant in VARIANTS:
        apply_settings(variant['settings'])
        if variant.get('exact'):
            schedule = exact_schedule(seed)
        else:
            schedule, _ = dpt.build_schedule(seed)
        dpt.check_schedule(schedule)
        write(to_json(variant, schedule, seed))
    apply_settings({})
    schedule = baseline_schedule()
    dpt.check_schedule(schedule)
    write(to_json(BASELINE, schedule, 0))


if __name__ == '__main__':
    main()
