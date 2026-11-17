# Generate Draft Predict Tap scoring workbooks, one per schedule in schedules/, that work the same in Google
# Sheets, LibreOffice and Excel.
#
#     python3 make_scoresheet.py                 # writes sheets/DPT <schedule>.xlsx for every supported schedule
#     python3 make_scoresheet.py two-cabs-24     # just one
#
# The layout and rules follow the original Google Sheets template (Participant List, Scores, Final Ranking,
# Draft Order and one draft sheet per round), but the workbook is built from scratch, sized to the event, and
# uses only functions all three apps evaluate the same way: IF, AND, OR, NOT, ISNA, IFERROR, INDEX, MATCH,
# COUNTIF, SUMIF, ROW. No array formulas, SEQUENCE, FILTER, IFS, bare IFNA, INDIRECT, OFFSET or pivot tables.
# Roles come from the optimized schedule, keyed to each participant's position on the Participant List.

import json
from copy import copy
import os
import sys
from typing import Dict, List

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as col
from openpyxl.worksheet.datavalidation import DataValidation

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_DIR = os.path.join(HERE, 'schedules')
OUT_DIR = os.path.join(HERE, 'sheets')

SCHEDULES = ['balanced-14', 'balanced-16', 'balanced-18', 'balanced', 'balanced-22', 'balanced-24',
             'balanced-26', 'two-cabs', 'two-cabs-22', 'two-cabs-24', 'two-cabs-26']

PLAYERS_PER_ROUND = 10
PICKS = 10
MAX_MAPS = 9

FONT = 'Arial'
BLUE = 'C9DAF8'
GOLD = 'FFF2CC'
INPUT = 'B6D7A8'      # green: cells the organizer edits
TURN = '00FF00'       # bright green: whose turn it is to draft
HEADER = 'D9D9D9'

PL = "'Participant List'"
SC = 'Scores'
DO = "'Draft Order'"
LISTS = 'Lists'


def fill(color: str) -> PatternFill:
    return PatternFill('solid', start_color=color, end_color=color)


def draft_sheet_name(r: int) -> str:
    return f'Round {r} Draft Sheet'


def ref(sheet_name: str) -> str:
    return f"'{sheet_name}'"


class Layout:
    """Cell positions shared between tabs, derived from the event size."""

    def __init__(self, schedule: Dict):
        self.schedule = schedule
        self.n = len(schedule['players'])
        self.rounds = len(schedule['rounds'])
        self.cabs = schedule['cabs']
        self.predictors = self.n - 2 - PLAYERS_PER_ROUND
        # Participant List rows
        self.pl_first = 5
        self.pl_last = self.pl_first + self.n - 1
        # Scores rows
        self.sc_round, self.sc_blue, self.sc_gold = 2, 3, 4
        self.sc_planners = 5
        self.sc_players = 7
        self.sc_predictors = self.sc_players + PLAYERS_PER_ROUND
        self.sc_last = self.sc_predictors + self.predictors - 1
        self.sc_winner = self.sc_last + 1
        self.sc_maps = self.sc_winner + 3
        self.sc_mode = self.sc_maps + 1
        self.sc_all_points = self.sc_mode + 1
        # Draft sheet rows
        self.ds_players = 7
        self.ds_picks = 20

    def name_col(self, r: int) -> str:
        return col(3 + 3 * (r - 1))

    def team_col(self, r: int) -> str:
        return col(4 + 3 * (r - 1))

    def points_col(self, r: int) -> str:
        return col(5 + 3 * (r - 1))

    def participant(self, k: int) -> str:
        """Formula for the name of participant number k (1-based) on the Participant List."""
        return f"INDEX({PL}!$B${self.pl_first}:$B${self.pl_last},{k})"

    def maps(self) -> str:
        return f'{SC}!$B${self.sc_maps}'

    def slot_label(self, r: int) -> str:
        if self.cabs == 1:
            return f'Round {r}'
        slot = (r - 1) // self.cabs + 1
        alone = r == self.rounds and self.rounds % self.cabs
        return f'Round {r}' + (' (alone, last)' if alone else f' (slot {slot}, cab {(r - 1) % self.cabs + 1})')


def style_header(cell, color: str = HEADER):
    cell.font = Font(name=FONT, bold=True)
    cell.fill = fill(color)
    cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)


def set_font(ws):
    """Arial everywhere, keeping each cell's bold, italic, size and color."""
    for row in ws.iter_rows():
        for c in row:
            if c.font.name != FONT:
                font = copy(c.font)
                font.name = FONT
                c.font = font


def team_colors(ws, cells: str, formula_cell: str = None):
    """Blue/gold fill: on the cells' own value, or on a formula relative to the range's top-left cell."""
    if formula_cell:
        ws.conditional_formatting.add(cells, FormulaRule(formula=[f'{formula_cell}="Blue"'], fill=fill(BLUE)))
        ws.conditional_formatting.add(cells, FormulaRule(formula=[f'{formula_cell}="Gold"'], fill=fill(GOLD)))
    else:
        ws.conditional_formatting.add(cells, CellIsRule(operator='equal', formula=['"Blue"'], fill=fill(BLUE)))
        ws.conditional_formatting.add(cells, CellIsRule(operator='equal', formula=['"Gold"'], fill=fill(GOLD)))


def list_validation(ws, cells: str, source: str, prompt: str = None):
    dv = DataValidation(type='list', formula1=source, allow_blank=True, showErrorMessage=True,
                        errorTitle='Invalid choice', error='Please pick a value from the dropdown.')
    if prompt:
        dv.showInputMessage, dv.prompt = True, prompt
    dv.add(cells)
    ws.add_data_validation(dv)


# ---------------------------------------------------------------- tabs

def build_instructions(ws, L: Layout):
    s = L.schedule
    tap = s['metrics']['tap_together']
    optimal = tap['sum_of_squares'] == tap['proven_lower_bound']
    cabs = 'one cab' if L.cabs == 1 else 'two cabs'
    lines = [
        f"Draft Predict Tap: {L.n} participants, {cabs}, {L.rounds} rounds",
        "",
        "How to use this sheet",
        "(If a cell isn't a dropdown, don't edit it. The only exception is the green cells on the "
        "\"Participant List\" tab.)",
        "",
        f"1. Enter exactly {L.n} unique participant names on the \"Participant List\" tab. Roles come from a fixed "
        "schedule keyed to each name's position in that list, so you can rename, shuffle or randomize the names, "
        "but don't add or remove rows.",
        "",
        "2. At the start of the game, have participants check the \"Participant List\" tab (or \"Scores\") to see "
        "which round they Plan. Each Planner finds their co-Planner and goes to that round's draft sheet. The draft "
        "sheet only offers Players who are still available, and highlights in green whose turn it is. Have everyone "
        "draft at the same time, so that every round is drafted before the first round begins.",
        "",
        "3. After drafting, Predictors go to the draft sheet of each round they predict and pick Blue or Gold next "
        "to their name. Do all predicting before the first round begins, too.",
        "",
        "4. Play! When a set ends, select the number of maps Blue won at the top of that round's column on the "
        "\"Scores\" tab (Gold's maps fill in automatically).",
        "",
        "5. When all rounds are done, the \"Final Ranking\" tab lists everyone by total score.",
        "",
        "Advanced controls",
        "",
        "1. Below the table on the \"Scores\" tab you can change the number of maps per set (any odd number "
        "from 1 to 9).",
        "",
        "2. Also below the table you can choose how Predictors score. By default they get the same points as the "
        "team they predicted (maps won). With \"All or nothing\" they get a fixed number of points if their team "
        "wins the set and nothing otherwise; pick the number of points next to it.",
        "",
        "3. On the \"Draft Order\" tab you can change the draft order; every draft sheet follows it.",
        "",
        "About the schedule",
        "",
        f"Everyone plays 5 rounds and plans once, and predicts in the remaining {L.rounds - 6} round"
        f"{'s' if L.rounds - 6 != 1 else ''}. How often each pair of participants plays together is "
        + ("proven to be as even as possible" if optimal else
           f"within {tap['sum_of_squares'] - tap['proven_lower_bound']} points of the proven optimum")
        + f"; pairs play together {tap['min']}-{tap['max']} times.",
    ]
    if L.cabs == 1:
        lines += ["",
                  f"Nobody sits out more than {s['metrics']['waits']['max']} rounds in a row between games, and "
                  "the later, more exciting rounds are shared out fairly. The rounds are independent, so you can "
                  "play them in any order (for example, skip a round whose Player is away and come back to it)."]
    else:
        solo = (f" Round {L.rounds} has no partner and is played alone at the end." if L.rounds % 2 else "")
        lines += ["",
                  "Two cabs: play Rounds 1 and 2 at the same time, then 3 and 4, and so on." + solo +
                  " The Players of the two rounds in each pair never overlap, so both games can run at once. "
                  "Planners and Predictors may be playing in the other game, so do all drafting and predicting "
                  "before the first pair starts."]
    lines += ["", f"Schedule: schedules/{s['name']}.json in the draft_predict_tap repository "
                  "(github.com/rrenaud/draft_predict_tap)."]
    ws.column_dimensions['A'].width = 110
    for i, line in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=line)
        c.alignment = Alignment(wrap_text=True, vertical='top')
        if i == 1:
            c.font = Font(name=FONT, bold=True, size=14)
        elif line in ('How to use this sheet', 'Advanced controls', 'About the schedule'):
            c.font = Font(name=FONT, bold=True, size=12)


def build_participant_list(ws, L: Layout):
    ws['A1'] = f"Edit the green cells with participant names. This sheet is scheduled for exactly {L.n} participants."
    ws['A1'].font = Font(name=FONT, bold=True)
    ws['A2'] = "It's safe to edit, clear, randomize or sort the green cells, but don't touch other cells."
    total_col = col(3 + L.rounds)
    rank_col = col(4 + L.rounds)
    roles_first = 6 + L.rounds
    ws.cell(row=4, column=1, value='#')
    ws.cell(row=4, column=2, value='Participants')
    for r in range(1, L.rounds + 1):
        ws.cell(row=4, column=2 + r, value=f'Round {r} Score')
        ws.cell(row=4, column=roles_first + r - 1, value=L.slot_label(r) if L.cabs > 1 else f'Round {r}')
    ws.cell(row=4, column=3 + L.rounds, value='Total Score')
    ws.cell(row=4, column=4 + L.rounds, value='Rank key')
    ws.cell(row=3, column=roles_first, value='Your role in each round:')
    ws.cell(row=3, column=roles_first).font = Font(name=FONT, bold=True)
    for c in range(1, roles_first + L.rounds):
        if ws.cell(row=4, column=c).value:
            style_header(ws.cell(row=4, column=c))
    ws.row_dimensions[4].height = 45 if L.cabs > 1 else 30

    for k in range(1, L.n + 1):
        row = L.pl_first + k - 1
        ws.cell(row=row, column=1, value=k)
        name = ws.cell(row=row, column=2, value=f'Participant{k}')
        name.fill = fill(INPUT)
        for r in range(1, L.rounds + 1):
            nc, pc = L.name_col(r), L.points_col(r)
            ws.cell(row=row, column=2 + r,
                    value=f'=SUMIF({SC}!${nc}${L.sc_planners}:${nc}${L.sc_last},$B{row},'
                          f'{SC}!${pc}${L.sc_planners}:${pc}${L.sc_last})')
            plan = f'{SC}!${nc}${L.sc_planners}:${nc}${L.sc_planners + 1}'
            play = f'{SC}!${nc}${L.sc_players}:${nc}${L.sc_predictors - 1}'
            role = (f'=IF($B{row}="","",IF(COUNTIF({plan},$B{row})>0,"Plan",'
                    f'IF(COUNTIF({play},$B{row})>0,"Play","Predict")))')
            ws.cell(row=row, column=roles_first + r - 1, value=role).alignment = Alignment(horizontal='center')
        ws.cell(row=row, column=3 + L.rounds, value=f'=SUM(C{row}:{col(2 + L.rounds)}{row})')
        # Unique rank: higher total first, ties broken by list order (used by Final Ranking).
        ws.cell(row=row, column=4 + L.rounds,
                value=f'=COUNTIF(${total_col}${L.pl_first}:${total_col}${L.pl_last},">"&{total_col}{row})'
                      f'+COUNTIF(${total_col}${L.pl_first}:{total_col}{row},{total_col}{row})')
    roles = f'{col(roles_first)}{L.pl_first}:{col(roles_first + L.rounds - 1)}{L.pl_last}'
    ws.conditional_formatting.add(roles, CellIsRule(operator='equal', formula=['"Play"'], fill=fill('F4CCCC')))
    ws.conditional_formatting.add(roles, CellIsRule(operator='equal', formula=['"Plan"'], fill=fill('D9EAD3')))

    count_row = L.pl_last + 2
    ws.cell(row=count_row, column=1, value='# Participants:')
    ws.cell(row=count_row, column=2, value=f'=COUNTA(B{L.pl_first}:B{L.pl_last})')
    ws.cell(row=count_row, column=3,
            value=f'=IF(B{count_row}={L.n},"","This sheet needs exactly {L.n} names; fill in every green cell.")')
    ws.cell(row=count_row, column=3).font = Font(name=FONT, bold=True, color='CC0000')
    ws.cell(row=count_row + 1, column=1, value='# Rounds:')
    ws.cell(row=count_row + 1, column=2, value=L.rounds)
    ws.cell(row=count_row + 2, column=1, value='# Predictors per round:')
    ws.cell(row=count_row + 2, column=2, value=L.predictors)
    ws.column_dimensions['A'].width = 22
    ws.column_dimensions['B'].width = 20
    for c in range(3, roles_first + L.rounds):
        ws.column_dimensions[col(c)].width = 11 if L.cabs == 1 else 12
    ws.column_dimensions[rank_col].hidden = True
    ws.freeze_panes = 'C5'


def build_scores(ws, L: Layout):
    ws['A1'] = 'Players, Planners & Predictors Score Sheet'
    ws['A1'].font = Font(name=FONT, bold=True, size=13)
    ws.cell(row=L.sc_blue, column=1, value='Select # of maps won by Blue (Gold is filled in)')
    ws.cell(row=L.sc_blue, column=1).alignment = Alignment(wrap_text=True)
    ws.cell(row=L.sc_blue, column=2, value='Blue').fill = fill(BLUE)
    ws.cell(row=L.sc_gold, column=2, value='Gold').fill = fill(GOLD)
    ws.cell(row=L.sc_planners, column=1, value='Planners')
    ws.cell(row=L.sc_planners, column=2, value='Blue')
    ws.cell(row=L.sc_planners + 1, column=2, value='Gold')
    ws.cell(row=L.sc_players, column=1, value='Players')
    if L.predictors:
        ws.cell(row=L.sc_predictors, column=1, value='Predictors')
    for label_row in (L.sc_planners, L.sc_players, L.sc_predictors):
        if label_row <= L.sc_last:
            ws.cell(row=label_row, column=1).font = Font(name=FONT, bold=True)

    index = {name: i + 1 for i, name in enumerate(L.schedule['players'])}
    blue_maps_dv = DataValidation(type='list', formula1=f'{LISTS}!$A$1:$A${MAX_MAPS + 1}', allow_blank=True,
                                  showErrorMessage=True, error='Pick a number of maps from the dropdown.')
    ws.add_data_validation(blue_maps_dv)
    for r in range(1, L.rounds + 1):
        rd = L.schedule['rounds'][r - 1]
        nc, tc, pc = L.name_col(r), L.team_col(r), L.points_col(r)
        ds = ref(draft_sheet_name(r))
        ws.merge_cells(f'{nc}{L.sc_round}:{pc}{L.sc_round}')
        style_header(ws[f'{nc}{L.sc_round}'])
        ws[f'{nc}{L.sc_round}'] = L.slot_label(r)
        blue, gold = f'{nc}${L.sc_blue}', f'{nc}${L.sc_gold}'
        ws.merge_cells(f'{nc}{L.sc_blue}:{pc}{L.sc_blue}')
        ws.merge_cells(f'{nc}{L.sc_gold}:{pc}{L.sc_gold}')
        ws[f'{nc}{L.sc_blue}'].fill = fill(BLUE)
        ws[f'{nc}{L.sc_gold}'].fill = fill(GOLD)
        ws[f'{nc}{L.sc_gold}'] = f'=IF({nc}{L.sc_blue}="","",IF({nc}{L.sc_blue}>{L.maps()},"Too many",' \
                                 f'{L.maps()}-{nc}{L.sc_blue}))'
        for c in (f'{nc}{L.sc_blue}', f'{nc}{L.sc_gold}'):
            ws[c].alignment = Alignment(horizontal='center')
            ws[c].font = Font(name=FONT, bold=True)
        blue_maps_dv.add(f'{nc}{L.sc_blue}')
        winner = f'{tc}${L.sc_winner}'

        def points(team_cell: str) -> str:
            return (f'=IF(OR({team_cell}="",{nc}${L.sc_blue}=""),"",'
                    f'IF({team_cell}="Blue",{blue},IF({team_cell}="Gold",{gold},"")))')

        names = rd['drafters'] + rd['tappers'] + rd['gamblers']
        for i, name in enumerate(names):
            row = L.sc_planners + i
            ws[f'{nc}{row}'] = f'={L.participant(index[name])}&""'
            if i < 2:
                ws[f'{tc}{row}'] = 'Blue' if i == 0 else 'Gold'
                ws[f'{pc}{row}'] = points(f'{tc}{row}')
            elif i < 2 + PLAYERS_PER_ROUND:
                ws[f'{tc}{row}'] = f"={ds}!$C${L.ds_players + i - 2}&\"\""
                ws[f'{pc}{row}'] = points(f'{tc}{row}')
            else:
                k = i - 2 - PLAYERS_PER_ROUND
                ws[f'{tc}{row}'] = f"={ds}!$F${L.ds_picks + k}&\"\""
                ws[f'{pc}{row}'] = (
                    f'=IF(OR({tc}{row}="",{nc}${L.sc_blue}=""),"",IF($B${L.sc_mode}="All or nothing",'
                    f'IF({tc}{row}={winner},$B${L.sc_all_points},0),IF({tc}{row}="Blue",{blue},{gold})))')
        ws[f'{nc}{L.sc_winner}'] = 'Winner:'
        ws[f'{tc}{L.sc_winner}'] = (f'=IF(OR({nc}{L.sc_blue}="",{nc}{L.sc_gold}="Too many"),"",'
                                    f'IF({nc}{L.sc_blue}>{nc}{L.sc_gold},"Blue",'
                                    f'IF({nc}{L.sc_gold}>{nc}{L.sc_blue},"Gold","")))')
        ws[f'{nc}{L.sc_winner + 1}'] = f'Draft or predict on "{draft_sheet_name(r)}"'
        ws[f'{nc}{L.sc_winner + 1}'].font = Font(name=FONT, italic=True, size=9)
        team_colors(ws, f'{tc}{L.sc_planners}:{tc}{L.sc_winner}')
        team_colors(ws, f'{nc}{L.sc_planners}:{nc}{L.sc_last}', f'{tc}{L.sc_planners}')
        team_colors(ws, f'{pc}{L.sc_planners}:{pc}{L.sc_last}', f'{tc}{L.sc_planners}')
        ws.column_dimensions[nc].width = 16
        ws.column_dimensions[tc].width = 7
        ws.column_dimensions[pc].width = 5

    # Settings
    ws.cell(row=L.sc_maps, column=1, value='# of maps in a set (odd, 1-9)')
    ws.cell(row=L.sc_maps, column=2, value=3).fill = fill(INPUT)
    list_validation(ws, f'B{L.sc_maps}', '"1,3,5,7,9"')
    ws.cell(row=L.sc_mode, column=1, value='Predictor scoring')
    ws.cell(row=L.sc_mode, column=2, value='1 point per map').fill = fill(INPUT)
    list_validation(ws, f'B{L.sc_mode}', '"1 point per map,All or nothing"')
    ws.cell(row=L.sc_mode, column=3, value='1 point per map: Predictors get the maps their team won. '
                                            'All or nothing: the points below if their team wins the set.')
    ws.cell(row=L.sc_all_points, column=1, value='All-or-nothing points')
    ws.cell(row=L.sc_all_points, column=2, value=1).fill = fill(INPUT)
    list_validation(ws, f'B{L.sc_all_points}', '"1,2,3,4,5,6,7,8,9"')
    for r in (L.sc_maps, L.sc_mode, L.sc_all_points):
        ws.cell(row=r, column=1).font = Font(name=FONT, bold=True)
    ws.column_dimensions['A'].width = 26
    ws.column_dimensions['B'].width = 16
    ws.freeze_panes = 'C5'


def build_final_ranking(ws, L: Layout):
    for c, h in enumerate(['Place', 'Participant', 'Total Score'], 1):
        style_header(ws.cell(row=1, column=c, value=h))
    total_col = col(3 + L.rounds)
    rank_col = col(4 + L.rounds)
    names = f'{PL}!$B${L.pl_first}:$B${L.pl_last}'
    totals = f'{PL}!${total_col}${L.pl_first}:${total_col}${L.pl_last}'
    keys = f'{PL}!${rank_col}${L.pl_first}:${rank_col}${L.pl_last}'
    for k in range(1, L.n + 1):
        row = k + 1
        ws.cell(row=row, column=2, value=f'=IFERROR(INDEX({names},MATCH({k},{keys},0)),"")')
        ws.cell(row=row, column=3, value=f'=IFERROR(INDEX({totals},MATCH({k},{keys},0)),"")')
        ws.cell(row=row, column=1, value=f'=IF(B{row}="","",COUNTIF({totals},">"&C{row})+1)')
    ws.column_dimensions['B'].width = 22
    ws.column_dimensions['C'].width = 12
    ws.conditional_formatting.add(f'A2:C{L.n + 1}', FormulaRule(formula=['$A2=1'], fill=fill('FFE599'),
                                                                font=Font(name=FONT, bold=True)))


def build_draft_order(ws, L: Layout):
    ws['A1'] = 'Suggested draft order:'
    ws['E1'] = 'Linear draft order'
    ws['G1'], ws['H1'] = 'Blue', 'Gold'
    suggested = [('Blue Planner picks first', 'B, G'), ('Gold Planner picks first', 'G, B'),
                 ('Gold Planner picks first', 'G, B'), ('Blue Planner picks first', 'B, G'),
                 ('Blue Planner picks first', 'B, G')]
    for i, (text, short) in enumerate(suggested):
        ws.cell(row=2 + i, column=1, value=f'Draft turn {i + 1}')
        ws.cell(row=2 + i, column=2, value=text)
        ws.cell(row=2 + i, column=3, value=short)
    order = ['Blue', 'Gold', 'Gold', 'Blue', 'Gold', 'Blue', 'Blue', 'Gold', 'Blue', 'Gold']
    for i, team in enumerate(order):
        row = 2 + i
        ws.cell(row=row, column=4, value=i + 1)
        ws.cell(row=row, column=5, value=team).fill = fill(INPUT)
        if i % 2:
            ws.cell(row=row, column=6, value=f'=IF(E{row}=E{row - 1},"WARNING: It is recommended for each '
                                             f'Planner to draft exactly once in each draft turn.","")')
    team_colors(ws, 'E2:E11')
    list_validation(ws, 'E2:E11', '"Blue,Gold"')
    ws['G2'] = '=COUNTIF($E$2:$E$11,G1)'
    ws['H2'] = '=COUNTIF($E$2:$E$11,H1)'
    ws['D13'] = ('=IF(AND(G2=5,H2=5),"","ERROR: Must have 5 Blue and 5 Gold. There are "&G2&" Blue and "'
                 '&H2&" Gold selected.")')
    ws['D13'].font = Font(name=FONT, bold=True, color='CC0000')
    notes = ['Organizer: edit the dropdowns in column E to use a different draft order.',
             'The suggested draft order works well when there are multiple queens and multiple speed warriors of '
             'similar strength.',
             'If 1 player is significantly stronger than all others, Blue might be overpowered and you might want '
             'to adjust the draft order to give Gold more power.',
             'If only 1 player is very new, Gold might be disadvantaged and you might want to adjust the draft '
             'order to give Gold more power.']
    for i, note in enumerate(notes):
        ws.cell(row=14 + i, column=1, value=note)
    ws.column_dimensions['A'].width = 14
    ws.column_dimensions['B'].width = 24
    ws.column_dimensions['F'].width = 30


def build_draft_sheet(ws, L: Layout, r: int):
    nc = L.name_col(r)
    ws['A1'], ws['B1'] = 'Round', r
    ws['A1'].font = ws['B1'].font = Font(name=FONT, bold=True, size=13)
    if L.cabs > 1:
        partner = r + 1 if r % 2 else r - 1
        ws['C1'] = (f'Played at the same time as Round {partner} on the other cab.' if partner <= L.rounds
                    else 'Played alone at the end.')
    ws['A3'], ws['B3'] = 'Blue Planner', 'Gold Planner'
    style_header(ws['A3'], BLUE)
    style_header(ws['B3'], GOLD)
    ws['A4'] = f'={SC}!${nc}${L.sc_planners}'
    ws['B4'] = f'={SC}!${nc}${L.sc_planners + 1}'
    ws['D3'] = "If it's not a dropdown, don't edit it!"
    ws['D3'].font = Font(name=FONT, bold=True, color='CC0000')

    first_pick, last_pick = L.ds_picks, L.ds_picks + PICKS - 1
    picks = f'$B${first_pick}:$B${last_pick}'
    ws['A6'] = 'Players'
    ws['A6'].font = Font(name=FONT, bold=True)
    for k in range(1, PLAYERS_PER_ROUND + 1):
        row = L.ds_players + k - 1
        ws.cell(row=row, column=1, value=k)
        ws.cell(row=row, column=2, value=f'={SC}!${nc}${L.sc_players + k - 1}')
        ws.cell(row=row, column=3, value=f'=IF(ISNA(MATCH(B{row},{picks},0)),"",'
                                         f'INDEX($A${first_pick}:$A${last_pick},MATCH(B{row},{picks},0)))')
    players = f'$B${L.ds_players}:$B${L.ds_players + PLAYERS_PER_ROUND - 1}'
    team_colors(ws, f'C{L.ds_players}:C{L.ds_players + 9}')
    team_colors(ws, f'B{L.ds_players}:B{L.ds_players + 9}', f'C{L.ds_players}')

    ws['E6'] = 'Teams'
    ws['E6'].font = Font(name=FONT, bold=True)
    ws['E8'], ws['F8'] = 'Blue', 'Gold'
    style_header(ws['E8'], BLUE)
    style_header(ws['F8'], GOLD)
    for k in range(1, 6):
        row = 8 + k
        ws.cell(row=row, column=4, value=k)
        for c in ('E', 'F'):
            # &"" keeps an undrafted pick blank (INDEX of an empty cell is 0 in LibreOffice and Excel).
            ws[f'{c}{row}'] = (f'=IFERROR(INDEX({picks},MATCH($D{row}&{c}$8,$I${first_pick}:$I${last_pick},0))'
                               f'&"","")')

    for c, h in (('A', 'Drafting Order'), ('B', 'Choose Player'), ('C', 'Errors')):
        style_header(ws[f'{c}{first_pick - 1}'])
        ws[f'{c}{first_pick - 1}'] = h
    # Hidden helpers: I = pick number within team ("1Blue"), M:V = how many of players 1..k are still available
    # before this pick, X:AG = the available players packed to the left (the dropdown's source).
    avail_first, list_first = 13, 24
    for j in range(PICKS):
        row = first_pick + j
        ws[f'A{row}'] = f"={DO}!E{2 + j}"
        ws[f'B{row}'].fill = PatternFill(fill_type=None)
        if j == 0:
            ws[f'C{row}'] = (f'=IF(B{row}="","",IF(COUNTIF({players},B{row})=0,'
                             f'"Not a Player in this round.",""))')
        else:
            ws[f'C{row}'] = (f'=IF(B{row}="","",IF(B{row - 1}="","Please wait your turn to draft.",'
                             f'IF(COUNTIF($B${first_pick}:B{row - 1},B{row})>0,'
                             f'"Player was already chosen! Please select a different Player.",'
                             f'IF(COUNTIF({players},B{row})=0,"Not a Player in this round.",""))))')
        ws[f'I{row}'] = f'=COUNTIF(A${first_pick}:A{row},A{row})&A{row}'
        for k in range(1, PLAYERS_PER_ROUND + 1):
            player = f'$B${L.ds_players + k - 1}'
            taken = '0' if j == 0 else f'COUNTIF($B${first_pick}:$B{row - 1},{player})'
            prev = '' if k == 1 else f'{col(avail_first + k - 2)}{row}+'
            ws.cell(row=row, column=avail_first + k - 1, value=f'={prev}IF({taken}=0,1,0)')
            ws.cell(row=row, column=list_first + k - 1,
                    value=f'=IFERROR(INDEX({players},MATCH({k},${col(avail_first)}{row}:'
                          f'${col(avail_first + 9)}{row},0)),"")')
        source = f'${col(list_first)}${row}:${col(list_first + 9)}${row}'
        list_validation(ws, f'B{row}', source)
    team_colors(ws, f'A{first_pick}:A{last_pick}')
    ws.conditional_formatting.add(f'B{first_pick}:B{last_pick}',
                                  FormulaRule(formula=[f'AND(B{first_pick}="",B{first_pick - 1}<>"")'],
                                              fill=fill(TURN)))
    for c in ['I'] + [col(c) for c in range(avail_first, list_first + 10)]:
        ws.column_dimensions[c].hidden = True

    # Predictors
    if L.predictors:
        ws[f'E{first_pick - 1}'], ws[f'F{first_pick - 1}'] = 'Predictors', 'Prediction'
        style_header(ws[f'E{first_pick - 1}'])
        style_header(ws[f'F{first_pick - 1}'])
        for k in range(L.predictors):
            row = first_pick + k
            ws[f'E{row}'] = f'={SC}!${nc}${L.sc_predictors + k}'
            ws[f'F{row}'].fill = fill(INPUT)
        list_validation(ws, f'F{first_pick}:F{first_pick + L.predictors - 1}', '"Blue,Gold"')
        team_colors(ws, f'F{first_pick}:F{first_pick + L.predictors - 1}')
    else:
        ws[f'E{first_pick - 1}'] = 'No Predictors in this game'
    note_row = max(last_pick, first_pick + L.predictors - 1) + 2
    ws[f'A{note_row}'] = "A bright green cell means it's that Planner's turn to draft a Player."
    ws[f'A{note_row + 1}'] = "Predictors: pick Blue or Gold next to your name before the first round starts."
    ws.column_dimensions['A'].width = 15
    ws.column_dimensions['B'].width = 18
    ws.column_dimensions['C'].width = 30
    ws.column_dimensions['E'].width = 18
    ws.column_dimensions['F'].width = 18


def build_lists(ws):
    for k in range(MAX_MAPS + 1):
        ws.cell(row=k + 1, column=1, value=f'=IF({k}<=Scores!$B$MAPS,{k},"")')
    ws.sheet_state = 'hidden'


def build_workbook(schedule: Dict) -> Workbook:
    L = Layout(schedule)
    assert L.predictors >= 0 and all(len(rd['tappers']) == PLAYERS_PER_ROUND for rd in schedule['rounds'])
    wb = Workbook()
    instructions = wb.active
    instructions.title = 'Instructions'
    build_instructions(instructions, L)
    build_participant_list(wb.create_sheet('Participant List'), L)
    build_scores(wb.create_sheet('Scores'), L)
    build_final_ranking(wb.create_sheet('Final Ranking'), L)
    build_draft_order(wb.create_sheet('Draft Order'), L)
    for r in range(1, L.rounds + 1):
        build_draft_sheet(wb.create_sheet(draft_sheet_name(r)), L, r)
    lists = wb.create_sheet(LISTS)
    build_lists(lists)
    for row in lists.iter_rows():
        for c in row:
            c.value = c.value.replace('$B$MAPS', f'$B${L.sc_maps}')
    for ws in wb.worksheets:
        set_font(ws)
    wb.calculation.fullCalcOnLoad = True
    return wb


def main(names: List[str]):
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in names or SCHEDULES:
        with open(os.path.join(SCHEDULE_DIR, name + '.json')) as f:
            schedule = json.load(f)
        path = os.path.join(OUT_DIR, f'DPT {name}.xlsx')
        build_workbook(schedule).save(path)
        print(path)


if __name__ == '__main__':
    main(sys.argv[1:])
