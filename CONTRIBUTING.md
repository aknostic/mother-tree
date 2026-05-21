# Contributing to Mother Tree

Thank you for taking the time to contribute.

## Filing an issue

Use the issue templates in `.github/ISSUE_TEMPLATE/`. Two types are available:

- **Bug report** — something is broken or behaving unexpectedly.
- **Feature request** — a new capability or change you would like to see.

For security-relevant issues, do not open a public issue. Email jurg@aknostic.com directly. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for the broader reporting policy.

## Development setup

### 1. Clone the repo

```bash
git clone https://github.com/mother-tree/mother-tree.git
cd mother-tree
```

### 2. Bring up the dev stack

The stack provides Postgres 17 + pgvector + PostGraphile:

```bash
docker compose up
```

Keep this running in a separate terminal while you work.

### 3. Install the Python toolchain

The project uses [`uv`](https://docs.astral.sh/uv/) — not pip directly. Install it first if you don't have it:

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
```

### 4. Smoke-test the CLI

```bash
uv run python -m cli --help
```

If that prints the help output, the setup is working.

## Running tests

```bash
uv run pytest jobs/tests/
```

Tests run against the compose-stack Postgres — there are no database mocks. Bring the stack up before running tests.

## Pull request conventions

- **Small, focused PRs.** One concern per PR.
- **Conventional commit prefixes** on commit messages and PR titles: `fix:`, `feat:`, `docs:`, `test:`, `rename:`, `remove:`, `deploy:`, `ci:`, `license:`.
- **Every behavior change includes a test.**
- **Run the full test suite before pushing:** `uv run pytest jobs/tests/`.
- One commit per PR is fine; multiple are also fine — what matters is that the diff is reviewable and the message describes the why.
- **Commit messages:** title line + optional body. No Co-Authored-By trailers or AI attribution lines.

## Code conventions

These conventions are enforced in the codebase. Don't violate them in a PR.

**GraphQL queries must use parameterized variables.** Never interpolate values with f-strings, even for internal IDs. The `jobs/mothertree/graphql_client.py` API enforces this pattern.

```python
# correct
client.execute(QUERY, {"id": user_id})

# wrong — never do this
client.execute(f"query {{ user(id: \"{user_id}\") {{ ... }} }}")
```

**Single path to CI data.** All queries against intelligence tables go through `jobs/mothertree/intelligence.py`. No direct GraphQL calls from bot characters, discipline jobs, or CLI commands.

**Prompts live next to their characters.** `jobs/bot/characters/saga.py`, `lena.py`, `mother_tree.py`, etc. Don't extract prompts to separate files.

**Tests use the real DB.** Don't mock the database. If a test needs data, use the compose stack and a fixture.

**No `print()` for user-facing output in long-running services.** Use the `log` module. CLI commands may use `print()` directly.

## Adding a persona

New persona characters live in `jobs/bot/characters/`. Pattern after [`saga.py`](jobs/bot/characters/saga.py) and [`lena.py`](jobs/bot/characters/lena.py) for the expected file shape: module docstring, `IDENTITY` constant, `respond()` function.

If the character draws on a real practitioner's published work, add a section to [`docs/inspirations.md`](docs/inspirations.md) crediting them.

Personas are archetypes, not impersonations.

## Documentation conventions

- Use Markdown. No HTML except for tables when Markdown can't express the layout.
- Code blocks for all CLI and shell commands.
- Cross-link to other docs with relative paths.

## Code of Conduct

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
