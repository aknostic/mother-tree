# test-data

Snapshot dumps of CI tables for testing pipeline stages independently.

Dumps are produced by `mothertree dump <path>` and restored with
`mothertree restore <path>`. They are not committed to this repository —
each deployment generates its own dumps from its own ingested content.

To produce a snapshot:

    uv run python -m cli dump test-data/my-snapshot.json

To restore one:

    uv run python -m cli restore test-data/my-snapshot.json
