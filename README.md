# patchx

Apply file edits idempotently, then commit and push. One small command
instead of a fresh heredoc patch script per change.

- [Install](#install)
- [Usage](#usage)
- [Ops](#ops)
- [JSON input](#json-input)
- [Run states](#run-states)
- [Known gaps](#known-gaps)
- [Docs](#docs)

## Install

Draft stage: single Python 3 file, standard library only, needs `git`.

~~~
git clone https://github.com/okureanthonytonny-commits/patchx ~/patchx
echo 'export PATH="$HOME/patchx:$PATH"' >> ~/.bashrc
source ~/.bashrc
patchx --help
~~~

## Usage

Run from anywhere inside the repo being patched, or pass `--repo DIR`.
File paths are relative to the repo root.

~~~
patchx replace FILE OLD NEW -m MSG [--regex]
patchx append  FILE TEXT    -m MSG
patchx create  FILE TEXT    -m MSG
patchx --json '<json>'
patchx --file ops.json
~~~

| Flag | Meaning |
|---|---|
| `-m, --message MSG` | commit message (required unless the json has `message`) |
| `--json JSON` | ops as a json string |
| `--file PATH` | ops as a json file |
| `--regex` | OLD is a regex (replace, shell form only) |
| `--repo DIR` | a directory inside the repo (default: current directory) |
| `--dry-run` | print the plan, write nothing |
| `--no-push` | commit but do not push |
| `-h, --help [TOPIC]` | help; topics: `schema` `ops` `states` `examples` |

Shell form is for one op, interactive use. Json is for several ops or
scripted use.

## Ops

- `replace` — `old` must match exactly once; that match becomes `new`.
  Literal by default, regex with `--regex` (json: `"regex": true`).
- `append` — add `text` as a new last line; creates the file if missing.
- `create` — write `text` to a new file; ABORT if it exists with
  different content.

All ops in a run are checked against current file content before
anything is written. One ABORT stops the whole run.

## JSON input

~~~
{
  "message": "commit message",
  "ops": [
    {"op": "replace", "file": "README.md", "old": "a", "new": "b", "regex": false},
    {"op": "append",  "file": "notes.txt", "text": "line"},
    {"op": "create",  "file": "a/b.txt",   "text": "content"}
  ]
}
~~~

A bare list of ops or a single op object is also accepted. File paths
are relative to the repo root.

## Run states

Per op: `SKIPPED` (already in HEAD), `COMMIT_ONLY` (on disk, not in
HEAD), `WRITE`, `ABORT`. Per run: `WRITTEN (<hash>: <message>)`,
`WRITTEN locally (...) but NOT pushed` (commit made, push failed),
`PUSHED (<n> earlier commit(s))`, `SKIPPED`, or `ABORT: <reason>`.
Exit 0 for WRITTEN, PUSHED and SKIPPED; 1 for ABORT or a failed push.
Re-running the same patch is safe, and resumes a failed push.

A commit contains only the files the run touched; other staged files
stay staged. A path ignored by `.gitignore` is an ABORT.

Push retries with backoff (2s base, 30s cap, 180s total) on transient
network errors only; auth/rejected errors fail immediately.

## Known gaps

- Draft. Exercised in a scratch repo only, not yet on a real project.
- "Already applied" is a substring check: if `new` (or the appended
  text) already appears anywhere in the file, the op counts as applied.
- Line endings are normalized to `\n` on write (CRLF files lose the `\r`).
- Pushes to the current branch's upstream; no remote/branch options.
- A shell-form argument starting with `-` is read as a flag; use json.
- No txt-file input, no anchor-bounded replace, no progress-log hash
  check yet. See `ideas.md`.

## Tests

~~~
python3 tests/test_patchx.py
~~~

Scratch repos and a local bare remote live under `tests/.scratch/`
(removed after each test); no network needed. `PATCHX_BIN=path` tests
another copy of the script.

## Docs

- [architecture.md](architecture.md) — how the file is laid out and why.
- [ideas.md](ideas.md) — deferred features and open questions.
