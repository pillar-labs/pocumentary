# Contributing to PoCumentary

Thanks for your interest in PoCumentary! This project is maintained with a
deliberately narrow scope, and we want to be upfront about what kinds of
contributions we can accept so you don't spend effort on something we'll have
to turn away.

## What we welcome

- **Feature requests** — open an [issue](https://github.com/pillar-labs/pocumentary/issues)
  describing what you'd like PoCumentary to do and why. We read every one, even
  if we can't act on all of them.
- **Bug fixes** — if you've found a bug, a pull request that fixes it is very
  welcome. Please include (or reference) a reproduction, and add a test that
  fails without your change and passes with it.

## What is out of scope

Anything beyond a feature request (as an issue) or a bug fix (as a PR) will not
be accepted. In particular, we generally will not merge:

- new features or large behavioral changes contributed as PRs (open an issue
  first so we can discuss whether it fits the project),
- refactors, restyling, or dependency churn that don't fix a specific bug, or
- changes that broaden PoCumentary's scope beyond spec-driven demo recording.

If you're unsure whether something fits, open an issue and ask before writing
code — we'd rather save you the work.

## Working on a bug fix

```bash
uv sync                # install dependencies (including the dev group)
uv run pytest          # run the test suite
```

Please keep pull requests focused on a single bug, match the surrounding code
style, and make sure the full test suite passes before you open the PR.

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE) that covers this project.
