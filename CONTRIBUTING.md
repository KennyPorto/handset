# Contributing

Thanks for wanting to help. Handset is a small project, so the process is light.

## Opening an issue

Go to [New issue](https://github.com/KennyPorto/handset/issues/new/choose) and pick one:

- **Bug report**: something doesn't work. The form asks for your phone, distribution and
  PipeWire version, and for the log. Before you paste logs, remove any phone numbers.
- **Feature idea**: something you'd like Handset to do.
- **Works (or not) with my phone**: no issue needed. Comment on
  [#2](https://github.com/KennyPorto/handset/issues/2) so others know which phones work.

## What happens next

Every issue goes onto the [Handset Roadmap](https://github.com/users/KennyPorto/projects/4)
board, where you can follow it:

**Backlog** (not planned yet) → **Ready** (planned) → **In progress** → **In review**
(being tested) → **Done** (shipped in a release)

Each one also gets a priority: **P0** is broken for users and gets fixed first, **P1** is
next up and **P2** is nice to have. Closing an issue moves it to Done on its own.

If I need more information, I'll ask in the issue. One that gets no reply for a month may be
closed, and you can reopen it any time.

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
