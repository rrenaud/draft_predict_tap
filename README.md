# draft_predict_tap
Killer Queen Mixer Metagame

This contains a little script for setting up the tournament.

The doc for how to play is here: https://docs.google.com/document/d/1shMuAlF4hN6pw2dyns2Txf5K19izcVoFRxeAkTF59eQ/edit

## Scheduling

- `main.py` prints a round-by-round role sheet (drafters, gamblers, tappers). It balances how often each pair
  of players taps together (with a proven lower bound to compare against), caps the wait between a player's
  games at 2 rounds and balances who gets to play the more valuable late rounds. Pure Python, no dependencies.
  `python3 main.py --cabs 2` schedules two cabinets: rounds run in parallel pairs (1+2, 3+4, ...) with disjoint
  tappers, and each round's drafters and gamblers are the other round's tappers. `--players N` (any even
  number from 14) schedules a different-size event with players / 2 rounds, so everyone still taps 5 times and drafts once.
- `exact_model.py` is an exact CP-SAT model (`pip install ortools`) used to prove what is achievable under a
  given wait limit.
- `sheets/` has ready-to-use scoring workbooks, one per schedule (14-26 players, one or two cabs): participant
  list, draft sheets with dropdowns of the Players still available, scores, final ranking and draft order. They
  work the same in Google Sheets (upload to Drive and open with Google Sheets), LibreOffice and Excel.
  `make_scoresheet.py` builds them from `schedules/` using only functions all three apps share.

## Tests

`python3 -m unittest discover tests` checks the generated workbooks (also run on every push by GitHub Actions):

- every formula uses only functions that Google Sheets, LibreOffice and Excel share;
- each round's Planners, Players and Predictors match the schedule;
- the committed `sheets/` files match what `make_scoresheet.py` builds now (rerun it after changes);
- with LibreOffice installed: every workbook recalculates without errors, and a simulated game in each one
  checks the draft dropdowns after every pick, the draft sheets' error messages, team lists, winners, totals,
  the Final Ranking and the role grid under both Predictor scoring modes.
- `generate_schedules.py` writes alternative schedules with different trade-offs to `schedules/`; see
  [schedules/README.md](schedules/README.md) for the comparison and critiques.
