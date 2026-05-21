## Summary

What does this change?

## Why

What problem does this solve, or what capability does it enable? Link related issues with `Fixes #N` or `Refs #N`.

## How it works

Brief description of the approach. Skip if obvious from the diff.

## Tests

- [ ] Tests pass locally (`uv run pytest jobs/tests/`)
- [ ] Behavior changes have new or updated tests
- [ ] No DB mocks introduced

## Documentation

- [ ] Doc updates included if behavior is user-visible
- [ ] CLAUDE.md / README.md updated if needed

## Checklist

- [ ] Commit messages follow the conventional prefix style (`fix:`, `feat:`, `docs:`, `test:`, etc.)
- [ ] No Co-Authored-By trailers in the commit messages
- [ ] GraphQL queries use parameterized variables (no f-string interpolation)
