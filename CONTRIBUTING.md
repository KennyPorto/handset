# Contributing

Thanks for wanting to help. Handset is a small project, so the process is light.

## Reporting a bug

Please include:

- your distribution and desktop, and the output of `pipewire --version`
- your phone model
- what you did, what you expected and what happened
- the output of `busctl --user tree org.pipewire.Telephony` while the phone is connected
- anything Handset printed, if you started it from a terminal
  (`flatpak run io.github.kennyporto.Handset`)

Before you paste logs, remove any phone numbers.

## Changing code

1. Set up the project as described under **Development** in the README.
2. Keep changes focused. One fix or feature per pull request is easiest to review.
3. Add or update tests in `tests/` for any logic in `handset/`.
4. Run `pytest` (GitHub runs it too on every pull request) and test a real call through the Flatpak build before opening the pull request.
5. Add a line to `CHANGELOG.md` under **Unreleased**.

Code style: standard Python (PEP 8, 100 columns) and Qt's QML conventions. Comments explain
*why*, not what.

## User-facing text

Write labels in title case for actions ("Connect Phone") and sentence case for everything else.
Keep messages short and say what the person can do next.
