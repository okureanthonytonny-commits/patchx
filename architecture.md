# patchx — architecture

Draft-stage design of the single-file `patchx` script. Everything lives
in one Python 3 file with no third-party imports; `git` is the only
external dependency.

## Flow

~~~
argv -> parse -> load_ops -> plan (per op) -> [dry-run stop]
     -> write files -> git add -> git commit -> git push (retry) -> result
~~~

Nothing touches disk until every op has been planned. The write, commit
and push steps only run if no op returned `ABORT`.

## Input

`load_ops()` turns any of the three input forms into one normalized
list of op dicts plus an optional commit message:

- shell form: `patchx replace|append|create ARGS...` builds a one-op
  dict from positional args (`--regex` sets `regex` on replace)
- `--json '<string>'`
- `--file path.json`

JSON may be an object with `ops` (and optional `message`), a bare list
of ops, or a single op object. Every op is checked for a known `op`
name and its required string fields before planning starts. `-m`
overrides a json `message`; a run with no message ABORTs.

## Ops

Each op is handled by one branch of `plan_op()`, which returns a state,
the new file content (for `WRITE` only), and a reason (for `ABORT`).

| Op | Required fields | Applies when |
|---|---|---|
| `replace` | file, old, new | `old` matches exactly once (regex optional) |
| `append` | file, text | text not already present; file created if missing |
| `create` | file, text | file absent, or present with identical content |

Adding an op means adding an entry to `REQ` and a branch in `plan_op()`.

## Planning and idempotency

`plan_op()` compares each op against two copies of the target file:
the working file on disk and `git show HEAD:<file>`.

| State | Meaning |
|---|---|
| `SKIPPED` | change already present in HEAD |
| `COMMIT_ONLY` | change on disk but not in HEAD |
| `WRITE` | change not applied yet; new content computed |
| `ABORT` | cannot apply |

`COMMIT_ONLY` is what lets a run resume after a write that succeeded
but a commit that failed (for example a missing git identity), instead
of reporting `SKIPPED` forever.

An op counts as "already applied" by substring check on `new` (replace)
or `text` (append). A replace with empty `new` counts as applied when
`old` no longer matches.

## Multi-op runs

Ops are planned in order against an in-memory overlay: the content an
earlier op in the same run would have produced. A later op on the same
file therefore sees the earlier op's result. Files are written from the
overlay only after all ops pass.

## Commit and push

- Files with state `WRITE` or `COMMIT_ONLY` are staged with `git add`;
  a failed add is an `ABORT`.
- The commit is scoped to those files (`git commit -- FILES`), so other
  staged files are left alone. It is made only if those files have
  staged changes.
- Push runs only if a commit was made or earlier local commits are
  unpushed. A push failure after a commit reports `WRITTEN locally ...
  NOT pushed` (exit 1); re-running resumes with `PUSHED (<n> earlier
  commit(s))`.
- Push retries on transient network errors (connection refused,
  timeout, temporary failure, unable to access) with exponential
  backoff: 2s base, 30s cap, 180s total. Each retry prints elapsed
  time. Any other error (auth, rejected, lock) fails immediately.
- `--no-push` stops after the commit.

## Help system

`HELP` is a dict of topic -> text. `--help` prints `main`;
`--help TOPIC` prints that topic (`schema`, `ops`, `states`,
`examples`). An unknown topic lists the valid ones. Help text lives in
the script so it ships with the tool and cannot drift from a separate
file.

## Exit codes

0 for `WRITTEN`, `PUSHED` and `SKIPPED`; 1 for any `ABORT` or a failed
push.

## Conventions

- The tool never deletes its own input; a `--file` json stays where it is.
- The repo root is resolved with `git rev-parse --show-toplevel` from
  `--repo` (default: current directory); paths in ops are relative to
  that root, so patchx works from any subdirectory.
- A path that `git check-ignore` reports as ignored is an `ABORT` at
  plan time, before anything is written.
- File and git I/O is UTF-8 regardless of locale.
- Code comments describe what code does; reasoning lives in these docs.
