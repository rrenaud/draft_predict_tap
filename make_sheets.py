# Make copies of the Draft Predict Tap scoring template (a Google Sheets workbook exported as .xlsx), one per
# schedule in schedules/, with the template's rotating role assignment replaced by the optimized schedule.
#
#     python3 make_sheets.py template.xlsx            # writes sheets/<schedule>.xlsx
#
# The template assigns roles on its "Scores" tab: each round is a 3-column block (name, team, points) and
# rows 5-26 hold, in order, 2 Planners (drafters), 10 Players (tappers) and up to 10 Predictors (gamblers).
# Each name cell computes INDEX(PARTICIPANTS_LIST, MOD(row + 2 * round - 3, NUM_PARTICIPANTS) + 1), a fixed
# rotation. This script rewrites only those cells as INDEX(PARTICIPANTS_LIST, k), where k is the participant's
# position in the schedule, so the names typed on the "Participant List" tab still flow through. It also sets
# the default name list to exactly as many placeholders as the schedule needs and adds a note to the
# instructions. Everything else (draft sheets, pivot table, validations, formatting) is left byte-for-byte.
#
# The template holds at most 22 participants (22 rows on "Scores", 11 round blocks), so schedules for 24 and 26
# players are skipped.
#
# Edits are made directly in the sheet XML rather than through openpyxl, which would rewrite the whole
# workbook and can drop Google-specific parts on the way back into Google Sheets.

import json
import os
import re
import sys
import zipfile
from typing import Dict, List
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEDULE_DIR = os.path.join(HERE, 'schedules')
OUT_DIR = os.path.join(HERE, 'sheets')

SCHEDULES = ['balanced-14', 'balanced-16', 'balanced-18', 'balanced', 'balanced-22', 'two-cabs', 'two-cabs-22']
MAX_PARTICIPANTS = 22
FIRST_ROW = 5  # Scores!C5 is the first name cell of round 1

SCORES_SHEET = 'xl/worksheets/sheet3.xml'
PARTICIPANTS_SHEET = 'xl/worksheets/sheet2.xml'
SHARED_STRINGS = 'xl/sharedStrings.xml'
WORKBOOK = 'xl/workbook.xml'
INSTRUCTIONS_STRING = 0   # shared string for 'TO Instructions And Tips'!A1
PARTICIPANTS_STRING = 2   # shared string for 'Participant List'!A1


def column_letter(index: int) -> str:
    """1 -> A, 27 -> AA."""
    letters = ''
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def replace_cell(xml: str, ref: str, new_cell: str) -> str:
    pattern = re.compile(r'<c r="%s"(?: [^>]*)?(?:/>|>.*?</c>)' % ref, re.S)
    xml, count = pattern.subn(lambda _: new_cell, xml, count=1)
    assert count == 1, f"cell {ref} not found"
    return xml


def cell_style(xml: str, ref: str) -> str:
    match = re.search(r'<c r="%s"((?: [^>/]*)?)' % ref, xml)
    assert match, f"cell {ref} not found"
    style = re.search(r' s="(\d+)"', match.group(1))
    return f' s="{style.group(1)}"' if style else ''


def formula_cell(ref: str, style: str, formula: str, cached: str) -> str:
    return f'<c r="{ref}"{style} t="str"><f>{escape(formula)}</f><v>{escape(cached)}</v></c>'


def round_rows(round_data: Dict, index: Dict[str, int]) -> List[int]:
    """Participant numbers (1-based) for rows 5-26 of one round: planners, players, predictors."""
    names = round_data['drafters'] + round_data['tappers'] + round_data['gamblers']
    return [index[name] + 1 for name in names]


def rewrite_scores(xml: str, schedule: Dict) -> str:
    index = {name: i for i, name in enumerate(schedule['players'])}
    for r in range(1, MAX_PARTICIPANTS // 2 + 1):
        col = column_letter(3 + 3 * (r - 1))
        rows = round_rows(schedule['rounds'][r - 1], index) if r <= len(schedule['rounds']) else []
        for k in range(MAX_PARTICIPANTS):
            ref = f'{col}{FIRST_ROW + k}'
            style = cell_style(xml, ref)
            if k < len(rows):
                formula = f'IF({col}$2="","",INDEX(PARTICIPANTS_LIST,{rows[k]}))'
                cell = formula_cell(ref, style, formula, f'Participant{rows[k]}')
            else:
                cell = formula_cell(ref, style, '""', '')
            xml = replace_cell(xml, ref, cell)
    return xml


def rewrite_participants(xml: str, count: int) -> str:
    for k in range(MAX_PARTICIPANTS):
        ref = f'B{FIRST_ROW + k}'
        style = cell_style(xml, ref)
        if k < count:
            cell = f'<c r="{ref}"{style} t="inlineStr"><is><t>Participant{k + 1}</t></is></c>'
        else:
            cell = f'<c r="{ref}"{style}/>'
        xml = replace_cell(xml, ref, cell)
    return xml


def rewrite_shared_string(xml: str, string_index: int, transform) -> str:
    items = list(re.finditer(r'<si>(.*?)</si>', xml, re.S))
    item = items[string_index]
    text = ''.join(re.findall(r'<t[^>]*>(.*?)</t>', item.group(1), re.S))
    new_item = f'<si><t xml:space="preserve">{transform(text)}</t></si>'
    return xml[:item.start()] + new_item + xml[item.end():]


def note_for(schedule: Dict) -> str:
    n, cabs, rounds = len(schedule['players']), schedule['cabs'], len(schedule['rounds'])
    tap = schedule['metrics']['tap_together']
    wait = schedule['metrics']['waits']['max']
    if tap['sum_of_squares'] == tap['proven_lower_bound']:
        balance = "proven to be as even as possible"
    else:
        balance = (f"within {tap['sum_of_squares'] - tap['proven_lower_bound']} points of the proven optimum "
                   f"(sum of squared pair counts {tap['sum_of_squares']} vs {tap['proven_lower_bound']})")
    lines = [
        f"THIS COPY: OPTIMIZED SCHEDULE FOR EXACTLY {n} PARTICIPANTS ON {'ONE CAB' if cabs == 1 else 'TWO CABS'} "
        f"({rounds} rounds).",
        "",
        f"Enter exactly {n} names on the \"Participant List\" tab. Roles on the \"Scores\" tab no longer rotate: "
        f"they come from a fixed schedule keyed to each name's position in that list. Everyone plays 5 rounds "
        f"and plans once. How often each pair of participants plays together is {balance}; pairs play together "
        f"{tap['min']}-{tap['max']} times.",
    ]
    if cabs == 1:
        lines.append(f"Nobody sits out more than {wait} rounds in a row between games, and the later, more "
                     f"exciting rounds are shared out fairly. Tip 3 below (parallel play on two cabs) does not "
                     f"apply to this copy; use the two-cab copy instead.")
    else:
        solo = f" Round {rounds} has no partner and is played alone at the end." if rounds % 2 else ""
        lines.append(f"Play Rounds 1 and 2 at the same time on the two cabs, then 3 and 4, and so on.{solo} The "
                     f"Players of the two rounds in each pair never overlap. Do all drafting and predicting "
                     f"before the first pair starts, as usual. Tip 3 below describes the original rotation and "
                     f"does not apply to this copy.")
    lines.append(f"Schedule source: schedules/{schedule['name']}.json in the draft_predict_tap repository.")
    return '\n'.join(lines) + '\n\n'


def make_copy(template: str, schedule: Dict, out_path: str):
    n = len(schedule['players'])
    with zipfile.ZipFile(template) as src, zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == SCORES_SHEET:
                data = rewrite_scores(data.decode('utf-8'), schedule).encode('utf-8')
            elif item.filename == PARTICIPANTS_SHEET:
                data = rewrite_participants(data.decode('utf-8'), n).encode('utf-8')
            elif item.filename == SHARED_STRINGS:
                xml = data.decode('utf-8')
                xml = rewrite_shared_string(xml, INSTRUCTIONS_STRING, lambda t: escape(note_for(schedule)) + t)
                xml = rewrite_shared_string(
                    xml, PARTICIPANTS_STRING,
                    lambda t: escape(f"Edit green cells with participant names. This copy is scheduled for "
                                     f"exactly {n} participants: enter exactly {n} names."))
                data = xml.encode('utf-8')
            elif item.filename == WORKBOOK:
                # Cached values elsewhere still reflect the template's rotation; recalculate when opened.
                data = data.replace(b'<calcPr/>', b'<calcPr fullCalcOnLoad="1"/>')
            dst.writestr(item, data)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__ or "usage: python3 make_sheets.py template.xlsx")
    os.makedirs(OUT_DIR, exist_ok=True)
    for name in SCHEDULES:
        with open(os.path.join(SCHEDULE_DIR, name + '.json')) as f:
            schedule = json.load(f)
        assert len(schedule['players']) <= MAX_PARTICIPANTS
        out_path = os.path.join(OUT_DIR, f'DPT {name}.xlsx')
        make_copy(sys.argv[1], schedule, out_path)
        print(out_path)


if __name__ == '__main__':
    main()
