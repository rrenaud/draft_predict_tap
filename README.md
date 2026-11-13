# draft_predict_tap
Killer Queen Mixer Metagame

This contains a little script for setting up the tournament.

The doc for how to play is here: https://docs.google.com/document/d/1shMuAlF4hN6pw2dyns2Txf5K19izcVoFRxeAkTF59eQ/edit

## Scheduling

- `main.py` prints a round-by-round role sheet (drafters, gamblers, tappers). It balances how often each pair
  of players taps together (with a proven lower bound to compare against), caps the wait between a player's
  games at 2 rounds and balances who gets to play the more valuable late rounds. Pure Python, no dependencies.
- `exact_model.py` is an exact CP-SAT model (`pip install ortools`) used to prove what is achievable under a
  given wait limit.
- `generate_schedules.py` writes alternative schedules with different trade-offs to `schedules/`; see
  [schedules/README.md](schedules/README.md) for the comparison and critiques.
