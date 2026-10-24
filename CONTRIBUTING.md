# Contributing

Contributions should preserve receive-only operation and privacy-by-default storage. Add tests for every new detection rule, mark unvalidated firmware behaviour clearly, and avoid claiming that spoofed MACs prove device identity. PR check: `cd collector && python -m pytest -q tests`.

Before adding radio or firmware features, reference official ESP-IDF APIs for the selected chip and specify which chip/PCB revisions were tested. The deployed sensor is C6; C5/5 GHz remains a separate unvalidated path. Submit hardware bring-up reports without private device identifiers or credentials.
