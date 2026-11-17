# End-to-end test of a generated scoring workbook, recalculated by LibreOffice: drafts rounds 1 and 2 pick by
# pick (checking each dropdown offers exactly the remaining Players), enters predictions and results, and checks
# totals, the Final Ranking, the role grid, team lists and winners under both Predictor scoring modes.
#
#     python3 test_scoresheet.py RECALC_SCRIPT WORK_DIR SCHEDULE_NAME
#
# RECALC_SCRIPT recalculates an .xlsx in place with LibreOffice and prints JSON with a "status" field.

import json, os, sys, subprocess, shutil, openpyxl
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_scoresheet as M
SK, V, name = sys.argv[1], sys.argv[2], sys.argv[3]
sched = json.load(open(os.path.join(HERE, 'schedules', f'{name}.json')))
L = M.Layout(sched)
idx = {n: i + 1 for i, n in enumerate(sched['players'])}
pname = lambda n: f'Participant{idx[n]}'
path = f'{V}/sim-{name}.xlsx'
shutil.copy(os.path.join(HERE, 'sheets', f'DPT {name}.xlsx'), path)
recalc = lambda: json.loads(subprocess.run([sys.executable, SK, path, '180'], capture_output=True, text=True).stdout)

# Draft rounds 1 and 2 one pick at a time, always choosing the LAST option the dropdown offers,
# so the availability list is exercised after every pick.
order = ['Blue', 'Gold', 'Gold', 'Blue', 'Gold', 'Blue', 'Blue', 'Gold', 'Blue', 'Gold']
picks = {1: [], 2: []}
for j in range(10):
    vals = openpyxl.load_workbook(path, data_only=True) if j else None
    wb = openpyxl.load_workbook(path)
    for r in (1, 2):
        ws = wb[M.draft_sheet_name(r)]
        row = L.ds_picks + j
        if j == 0:
            offered = [pname(n) for n in sched['rounds'][r - 1]['tappers']]
        else:
            vs = vals[M.draft_sheet_name(r)]
            offered = [vs.cell(row=row, column=24 + k).value for k in range(10)]
            offered = [o for o in offered if o]
        expected = [pname(n) for n in sched['rounds'][r - 1]['tappers'] if pname(n) not in picks[r]]
        assert sorted(offered) == sorted(expected), (r, j, offered, expected)
        choice = offered[-1]
        picks[r].append(choice)
        ws[f'B{row}'] = choice
    if j == 9:
        # predictions, results and scoring mode
        for r in (1, 2):
            ws = wb[M.draft_sheet_name(r)]
            for k in range(L.predictors):
                ws[f'F{L.ds_picks + k}'] = 'Blue' if k % 2 == 0 else 'Gold'
        sc = wb['Scores']
        sc[f'{L.name_col(1)}{L.sc_blue}'] = 2   # round 1: Blue wins 2-1
        sc[f'{L.name_col(2)}{L.sc_blue}'] = 1   # round 2: Gold wins 2-1
    wb.save(path)
    res = recalc()
    assert res.get('status') == 'success', res

# Expected scores (round 1 per-map predictor scoring; then check round 2 with all-or-nothing separately)
def expected(mode, aon=1):
    pts = {n: 0 for n in sched['players']}
    for r, blue in ((1, 2), (2, 1)):
        rd = sched['rounds'][r - 1]; gold = 3 - blue
        team = {}
        for j, p in enumerate(picks[r]): team[p] = order[j]
        get = lambda t: blue if t == 'Blue' else gold
        pts[rd['drafters'][0]] += blue; pts[rd['drafters'][1]] += gold
        for n in rd['tappers']: pts[n] += get(team[pname(n)])
        winner = 'Blue' if blue > gold else 'Gold'
        for k, n in enumerate(rd['gamblers']):
            pred = 'Blue' if k % 2 == 0 else 'Gold'
            pts[n] += get(pred) if mode == 'map' else (aon if pred == winner else 0)
    return {pname(n): v for n, v in pts.items()}

def check(mode, aon=1):
    wb = openpyxl.load_workbook(path, data_only=True)
    pl, fr, sc = wb['Participant List'], wb['Final Ranking'], wb['Scores']
    tcol = 3 + L.rounds
    got = {pl.cell(row=L.pl_first + i, column=2).value: pl.cell(row=L.pl_first + i, column=tcol).value for i in range(L.n)}
    exp = expected(mode, aon)
    assert got == exp, [(k, got[k], exp[k]) for k in exp if got[k] != exp[k]][:5]
    ranking = [(fr.cell(row=k + 2, column=1).value, fr.cell(row=k + 2, column=2).value, fr.cell(row=k + 2, column=3).value) for k in range(L.n)]
    assert sorted(n for _, n, _ in ranking) == sorted(exp)
    assert [t for _, _, t in ranking] == sorted(exp.values(), reverse=True)
    assert all(place == 1 + sum(v > t for v in exp.values()) for place, _, t in ranking)
    # roles grid
    first = 6 + L.rounds
    for i, n in enumerate(sched['players']):
        for r, rd in enumerate(sched['rounds'], 1):
            want = 'Plan' if n in rd['drafters'] else 'Play' if n in rd['tappers'] else 'Predict'
            assert pl.cell(row=L.pl_first + idx[n] - 1, column=first + r - 1).value == want
    # teams on draft sheet and winner
    d1 = wb[M.draft_sheet_name(1)]
    blue_team = [d1[f'E{9 + k}'].value for k in range(5)]
    assert blue_team == [p for j, p in enumerate(picks[1]) if order[j] == 'Blue'], blue_team
    assert sc[f'{L.team_col(1)}{L.sc_winner}'].value == 'Blue' and sc[f'{L.team_col(2)}{L.sc_winner}'].value == 'Gold'
    return ranking[:3]

print('per-map scoring OK, top 3:', check('map'))
wb = openpyxl.load_workbook(path); wb['Scores'][f'B{L.sc_mode}'] = 'All or nothing'; wb['Scores'][f'B{L.sc_all_points}'] = 4; wb.save(path)
assert recalc().get('status') == 'success'
print('all-or-nothing (4 pts) OK, top 3:', check('aon', 4))
