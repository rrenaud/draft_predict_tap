# Tests for the generated scoring workbooks (make_scoresheet.py).
#
#     python3 -m unittest discover tests            # from the repository root
#
# The first group runs anywhere. The second group recalculates workbooks with LibreOffice (soffice must be on
# PATH; those tests are skipped otherwise) and plays a simulated game through every workbook: a full draft, the
# draft sheets' error messages, predictions, results and both Predictor scoring modes.

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter

import openpyxl
from openpyxl.worksheet.formula import ArrayFormula

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import make_scoresheet as M  # noqa: E402

# Functions that Google Sheets, LibreOffice and Excel all evaluate the same way. Anything else must be justified
# before it is added here: SEQUENCE, FILTER, IFS, bare IFNA, INDIRECT and OFFSET all broke the original template
# outside Google Sheets.
ALLOWED_FUNCTIONS = {'IF', 'AND', 'OR', 'NOT', 'ISNA', 'IFERROR', 'INDEX', 'MATCH', 'COUNTIF', 'SUMIF', 'SUM',
                     'COUNTA'}
ERROR_VALUES = ('#NAME?', '#VALUE!', '#REF!', '#DIV/0!', '#N/A', '#NUM!', '#NULL!', 'Err:')
DRAFT_ORDER = ['Blue', 'Gold', 'Gold', 'Blue', 'Gold', 'Blue', 'Blue', 'Gold', 'Blue', 'Gold']
SOFFICE = shutil.which('soffice') or shutil.which('libreoffice')


def load_schedule(name):
    with open(os.path.join(ROOT, 'schedules', name + '.json')) as f:
        return json.load(f)


def formulas(wb):
    """(sheet, cell, formula text) for every formula cell, including data validation sources."""
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, ArrayFormula):
                    yield ws.title, c.coordinate, v
                elif isinstance(v, str) and v.startswith('='):
                    yield ws.title, c.coordinate, v
        for dv in ws.data_validations.dataValidation:
            yield ws.title, f'validation {dv.sqref}', dv.formula1 or ''


def recalculate(path, out_dir):
    """Open the workbook in headless LibreOffice, which computes every formula, and save the result."""
    profile = tempfile.mkdtemp(prefix='lo-profile-')
    try:
        subprocess.run([SOFFICE, f'-env:UserInstallation=file://{profile}', '--headless', '--calc',
                        '--convert-to', 'xlsx', '--outdir', out_dir, path],
                       check=True, capture_output=True, timeout=300)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    return openpyxl.load_workbook(os.path.join(out_dir, os.path.basename(path)), data_only=True)


class StaticTests(unittest.TestCase):
    """Checks that need no spreadsheet app."""

    def test_only_portable_functions(self):
        for name in M.SCHEDULES:
            wb = M.build_workbook(load_schedule(name))
            for sheet, cell, f in formulas(wb):
                with self.subTest(schedule=name, sheet=sheet, cell=cell):
                    self.assertNotIsInstance(f, ArrayFormula, 'array formulas behave differently across apps')
                    used = set(re.findall(r'([A-Z][A-Z0-9.]*)\(', re.sub(r'"[^"]*"', '""', f)))
                    self.assertLessEqual(used, ALLOWED_FUNCTIONS, f'non-portable function in {f}')
                    self.assertNotIn('[', f, 'link to another workbook')

    def test_roles_follow_the_schedule(self):
        for name in M.SCHEDULES:
            schedule = load_schedule(name)
            L = M.Layout(schedule)
            index = {n: i + 1 for i, n in enumerate(schedule['players'])}
            ws = M.build_workbook(schedule)['Scores']
            for r, rd in enumerate(schedule['rounds'], 1):
                expected = [index[n] for n in rd['drafters'] + rd['tappers'] + rd['gamblers']]
                got = [int(re.search(r',(\d+)\)&""$', ws[f'{L.name_col(r)}{L.sc_planners + i}'].value).group(1))
                       for i in range(len(expected))]
                with self.subTest(schedule=name, round=r):
                    self.assertEqual(got, expected)
            with self.subTest(schedule=name, check='everyone plans once and plays 5 rounds'):
                plans = Counter(n for rd in schedule['rounds'] for n in rd['drafters'])
                plays = Counter(n for rd in schedule['rounds'] for n in rd['tappers'])
                self.assertEqual(set(plans.values()), {1})
                self.assertEqual(set(plays.values()), {5})

    def test_committed_sheets_are_up_to_date(self):
        """sheets/*.xlsx must match what make_scoresheet.py builds now; rerun it after changing either."""
        for name in M.SCHEDULES:
            path = os.path.join(ROOT, 'sheets', f'DPT {name}.xlsx')
            with self.subTest(schedule=name):
                self.assertTrue(os.path.exists(path), f'{path} is missing; run make_scoresheet.py')
                committed = openpyxl.load_workbook(path)
                fresh = M.build_workbook(load_schedule(name))
                self.assertEqual(committed.sheetnames, fresh.sheetnames)
                for ws in fresh.worksheets:
                    other = committed[ws.title]
                    for row in ws.iter_rows():
                        for c in row:
                            if c.value not in (None, ''):  # empty strings are saved as empty cells
                                self.assertEqual(other[c.coordinate].value, c.value,
                                                 f'{ws.title}!{c.coordinate} differs; run make_scoresheet.py')


@unittest.skipUnless(SOFFICE, 'LibreOffice (soffice) is not installed')
class LibreOfficeTests(unittest.TestCase):
    """Recalculate real workbooks in LibreOffice and check the results."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='dpt-test-')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_recalculates_without_errors(self):
        for name in M.SCHEDULES:
            path = os.path.join(self.tmp, f'{name}.xlsx')
            M.build_workbook(load_schedule(name)).save(path)
            out = os.path.join(self.tmp, 'out')
            wb = recalculate(path, out)
            errors = [f'{ws.title}!{c.coordinate}={c.value}' for ws in wb.worksheets for row in ws.iter_rows()
                      for c in row if isinstance(c.value, str) and c.value.startswith(ERROR_VALUES)]
            with self.subTest(schedule=name):
                self.assertEqual(errors, [])

    def test_simulated_game(self):
        for name in M.SCHEDULES:
            with self.subTest(schedule=name):
                self.play_game(name)

    def play_game(self, name):
        schedule = load_schedule(name)
        L = M.Layout(schedule)
        index = {n: i + 1 for i, n in enumerate(schedule['players'])}
        label = {n: f'Participant{index[n]}' for n in schedule['players']}
        path = os.path.join(self.tmp, f'{name}.xlsx')
        wb = M.build_workbook(schedule)

        # Rounds 1 and 2: a full draft (in reverse list order) and predictions.
        picks = {}
        for r in (1, 2):
            ws = wb[M.draft_sheet_name(r)]
            picks[r] = [label[n] for n in reversed(schedule['rounds'][r - 1]['tappers'])]
            for j, p in enumerate(picks[r]):
                ws[f'B{L.ds_picks + j}'] = p
            for k in range(L.predictors):
                ws[f'F{L.ds_picks + k}'] = 'Blue' if k % 2 == 0 else 'Gold'
        # Round 3: a pick out of turn. Round 4: the same Player picked twice.
        round3, round4 = wb[M.draft_sheet_name(3)], wb[M.draft_sheet_name(4)]
        round3[f'B{L.ds_picks + 1}'] = label[schedule['rounds'][2]['tappers'][0]]
        twice = label[schedule['rounds'][3]['tappers'][0]]
        round4[f'B{L.ds_picks}'] = round4[f'B{L.ds_picks + 1}'] = twice
        # Results: Blue wins round 1 2-1, Gold wins round 2 2-1 (3 maps per set).
        wb['Scores'][f'{L.name_col(1)}{L.sc_blue}'] = 2
        wb['Scores'][f'{L.name_col(2)}{L.sc_blue}'] = 1
        wb.save(path)
        out = recalculate(path, os.path.join(self.tmp, 'out'))

        for r in (1, 2):
            ds = out[M.draft_sheet_name(r)]
            players = [label[n] for n in schedule['rounds'][r - 1]['tappers']]
            for j in range(M.PICKS):
                row = L.ds_picks + j
                offered = [ds.cell(row=row, column=24 + k).value for k in range(10)]
                offered = [o for o in offered if o]
                self.assertCountEqual(offered, [p for p in players if p not in picks[r][:j]],
                                      f'round {r}: dropdown before pick {j + 1}')
                self.assertIn(ds[f'C{row}'].value, (None, ''), f'round {r}: unexpected error on pick {j + 1}')
            blue = [ds[f'E{9 + k}'].value for k in range(5)]
            gold = [ds[f'F{9 + k}'].value for k in range(5)]
            self.assertEqual(blue, [p for j, p in enumerate(picks[r]) if DRAFT_ORDER[j] == 'Blue'])
            self.assertEqual(gold, [p for j, p in enumerate(picks[r]) if DRAFT_ORDER[j] == 'Gold'])
        self.assertEqual(out[M.draft_sheet_name(3)][f'C{L.ds_picks + 1}'].value, 'Please wait your turn to draft.')
        self.assertEqual(out[M.draft_sheet_name(4)][f'C{L.ds_picks + 1}'].value,
                         'Player was already chosen! Please select a different Player.')
        scores = out['Scores']
        self.assertEqual(scores[f'{L.team_col(1)}{L.sc_winner}'].value, 'Blue')
        self.assertEqual(scores[f'{L.team_col(2)}{L.sc_winner}'].value, 'Gold')
        self.check_totals(out, schedule, L, picks, label, 'per map')

        # Switch Predictors to all-or-nothing scoring, worth 4 points.
        wb['Scores'][f'B{L.sc_mode}'] = 'All or nothing'
        wb['Scores'][f'B{L.sc_all_points}'] = 4
        wb.save(path)
        out = recalculate(path, os.path.join(self.tmp, 'out'))
        self.check_totals(out, schedule, L, picks, label, 'all or nothing', 4)

    def check_totals(self, out, schedule, L, picks, label, mode, all_points=0):
        expected = {label[n]: 0 for n in schedule['players']}
        for r, blue in ((1, 2), (2, 1)):
            rd, gold = schedule['rounds'][r - 1], 3 - blue
            maps = {'Blue': blue, 'Gold': gold}
            team = {p: DRAFT_ORDER[j] for j, p in enumerate(picks[r])}
            expected[label[rd['drafters'][0]]] += blue
            expected[label[rd['drafters'][1]]] += gold
            for n in rd['tappers']:
                expected[label[n]] += maps[team[label[n]]]
            for k, n in enumerate(rd['gamblers']):
                predicted = 'Blue' if k % 2 == 0 else 'Gold'
                won = (blue > gold) == (predicted == 'Blue')
                expected[label[n]] += maps[predicted] if mode == 'per map' else (all_points if won else 0)

        pl, ranking = out['Participant List'], out['Final Ranking']
        total_col = 3 + L.rounds
        totals = {pl.cell(row=L.pl_first + i, column=2).value: pl.cell(row=L.pl_first + i, column=total_col).value
                  for i in range(L.n)}
        self.assertEqual(totals, expected, mode)
        rows = [[ranking.cell(row=k + 2, column=c).value for c in (1, 2, 3)] for k in range(L.n)]
        self.assertCountEqual([name for _, name, _ in rows], expected, mode)
        self.assertEqual([t for _, _, t in rows], sorted(expected.values(), reverse=True), mode)
        for place, _, total in rows:
            self.assertEqual(place, 1 + sum(v > total for v in expected.values()), mode)
        first = 6 + L.rounds
        for n in schedule['players']:
            for r, rd in enumerate(schedule['rounds'], 1):
                role = 'Plan' if n in rd['drafters'] else 'Play' if n in rd['tappers'] else 'Predict'
                self.assertEqual(pl.cell(row=L.pl_first + int(label[n][11:]) - 1, column=first + r - 1).value,
                                 role, f'{label[n]} round {r}')


if __name__ == '__main__':
    unittest.main()
