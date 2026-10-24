# Contributing

Contributions should preserve receive-only operation and privacy-by-default storage. Add tests for every new detection rule, mark unvalidated firmware behaviour clearly, and avoid claiming that spoofed MACs prove device identity. PR check: `cd collector && python -m pytest -q tests`.

Before adding radio or firmware features, reference official ESP-IDF C5 APIs and specify which chip/PCB revisions were tested. Submit an isolated hardware bring-up report without real device MAC addresses or credentials.
