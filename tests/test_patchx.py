import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PATCHX = os.environ.get("PATCHX_BIN") or os.path.join(os.path.dirname(HERE), "patchx")
SCRATCH = os.path.join(HERE, ".scratch")


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, encoding="utf-8")


class PatchxCase(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCRATCH, exist_ok=True)
        self.tmp = tempfile.mkdtemp(dir=SCRATCH)
        self.remote = os.path.join(self.tmp, "remote.git")
        self.work = os.path.join(self.tmp, "work")
        sh(self.tmp, "git", "init", "--bare", "-q", self.remote)
        sh(self.tmp, "git", "clone", "-q", self.remote, self.work)
        sh(self.work, "git", "symbolic-ref", "HEAD", "refs/heads/main")
        for k, v in (("user.name", "t"), ("user.email", "t@example.com"),
                     ("commit.gpgsign", "false")):
            sh(self.work, "git", "config", k, v)
        self.write("seed.txt", "alpha\nbeta\n")
        sh(self.work, "git", "add", ".")
        sh(self.work, "git", "commit", "-q", "-m", "seed")
        sh(self.work, "git", "push", "-q", "-u", "origin", "main")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        try:
            os.rmdir(SCRATCH)
        except OSError:
            pass

    def write(self, rel, text):
        path = os.path.join(self.work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.work, rel), encoding="utf-8") as f:
            return f.read()

    def px(self, *args, cwd=None, env=None):
        r = subprocess.run([sys.executable, PATCHX] + list(args),
                           cwd=cwd or self.work, capture_output=True,
                           encoding="utf-8", env=env)
        return r.returncode, r.stdout + r.stderr

    def local_count(self):
        return int(sh(self.work, "git", "rev-list", "--count", "HEAD").stdout)

    def remote_count(self):
        r = sh(self.tmp, "git", "--git-dir", self.remote, "rev-list",
               "--count", "main")
        return int(r.stdout)


class TestOps(PatchxCase):
    def test_replace_commits_and_pushes(self):
        rc, out = self.px("replace", "seed.txt", "alpha", "ALPHA", "-m", "m1")
        self.assertEqual(rc, 0, out)
        self.assertIn("WRITTEN (", out)
        self.assertEqual(self.read("seed.txt"), "ALPHA\nbeta\n")
        self.assertEqual(self.remote_count(), 2)

    def test_replace_rerun_is_skipped(self):
        self.px("replace", "seed.txt", "alpha", "ALPHA", "-m", "m1")
        rc, out = self.px("replace", "seed.txt", "alpha", "ALPHA", "-m", "m1")
        self.assertEqual(rc, 0, out)
        self.assertIn("SKIPPED", out)
        self.assertEqual(self.local_count(), 2)

    def test_commit_only_resumes(self):
        self.write("seed.txt", "ALPHA\nbeta\n")
        rc, out = self.px("replace", "seed.txt", "alpha", "ALPHA", "-m", "m1")
        self.assertEqual(rc, 0, out)
        self.assertIn("COMMIT_ONLY", out)
        self.assertIn("WRITTEN (", out)
        self.assertEqual(self.remote_count(), 2)

    def test_replace_aborts_on_zero_and_many_matches(self):
        rc, out = self.px("replace", "seed.txt", "zzz", "q", "-m", "m")
        self.assertEqual(rc, 1)
        self.assertIn("matched 0 times", out)
        self.write("seed.txt", "x\nx\n")
        rc, out = self.px("replace", "seed.txt", "x", "y", "-m", "m")
        self.assertEqual(rc, 1)
        self.assertIn("matched 2 times", out)
        self.assertEqual(self.read("seed.txt"), "x\nx\n")

    def test_replace_regex(self):
        rc, out = self.px("replace", "seed.txt", "al[a-z]+", "ALPHA",
                          "--regex", "-m", "m")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read("seed.txt"), "ALPHA\nbeta\n")

    def test_append_creates_then_adds_and_is_idempotent(self):
        rc, out = self.px("append", "notes.txt", "line1", "-m", "m")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read("notes.txt"), "line1\n")
        rc, out = self.px("append", "notes.txt", "line1", "-m", "m")
        self.assertIn("SKIPPED", out)
        self.px("append", "notes.txt", "line2", "-m", "m")
        self.assertEqual(self.read("notes.txt"), "line1\nline2\n")

    def test_create(self):
        rc, out = self.px("create", "a/b.txt", "hello", "-m", "m")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read("a/b.txt"), "hello")
        rc, out = self.px("create", "a/b.txt", "hello", "-m", "m")
        self.assertIn("SKIPPED", out)
        rc, out = self.px("create", "a/b.txt", "other", "-m", "m")
        self.assertEqual(rc, 1)
        self.assertIn("different content", out)

    def test_multi_op_is_all_or_nothing(self):
        ops = {"message": "m", "ops": [
            {"op": "replace", "file": "seed.txt", "old": "alpha", "new": "ALPHA"},
            {"op": "replace", "file": "seed.txt", "old": "zzz", "new": "q"}]}
        rc, out = self.px("--json", json.dumps(ops))
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.read("seed.txt"), "alpha\nbeta\n")
        self.assertEqual(self.local_count(), 1)

    def test_dry_run_writes_nothing(self):
        rc, out = self.px("replace", "seed.txt", "alpha", "ALPHA", "-m", "m",
                          "--dry-run")
        self.assertEqual(rc, 0, out)
        self.assertIn("DRY RUN", out)
        self.assertEqual(self.read("seed.txt"), "alpha\nbeta\n")

    def test_message_required(self):
        rc, out = self.px("replace", "seed.txt", "alpha", "ALPHA")
        self.assertEqual(rc, 1)
        self.assertIn("commit message required", out)

    def test_help_topics(self):
        rc, out = self.px("--help", "schema")
        self.assertEqual(rc, 0)
        self.assertIn("json schema", out)
        rc, out = self.px("--help", "nope")
        self.assertEqual(rc, 1)
        self.assertIn("unknown help topic", out)


class TestGitHandling(PatchxCase):
    def test_runs_from_a_subdirectory(self):
        sub = os.path.join(self.work, "sub")
        os.makedirs(sub)
        rc, out = self.px("replace", "seed.txt", "alpha", "ALPHA", "-m", "m",
                          cwd=sub)
        self.assertEqual(rc, 0, out)
        self.assertIn("WRITTEN (", out)
        rc, out = self.px("replace", "seed.txt", "alpha", "ALPHA", "-m", "m",
                          cwd=sub)
        self.assertIn("SKIPPED", out)

    def test_push_failure_reports_written_locally_then_resumes(self):
        sh(self.work, "git", "remote", "set-url", "origin",
           os.path.join(self.tmp, "nope.git"))
        args = ("replace", "seed.txt", "alpha", "ALPHA", "-m", "m")
        rc, out = self.px(*args)
        self.assertEqual(rc, 1, out)
        self.assertIn("WRITTEN locally", out)
        self.assertIn("NOT pushed", out)
        self.assertNotIn("ABORT", out)
        sh(self.work, "git", "remote", "set-url", "origin", self.remote)
        rc, out = self.px(*args)
        self.assertEqual(rc, 0, out)
        self.assertIn("PUSHED (1 earlier commit(s))", out)
        self.assertEqual(self.remote_count(), 2)

    def test_no_push_then_push(self):
        args = ("replace", "seed.txt", "alpha", "ALPHA", "-m", "m")
        rc, out = self.px(*args, "--no-push")
        self.assertEqual(rc, 0, out)
        self.assertIn("WRITTEN (", out)
        self.assertEqual(self.remote_count(), 1)
        rc, out = self.px(*args)
        self.assertIn("PUSHED (1 earlier commit(s))", out)
        self.assertEqual(self.remote_count(), 2)

    def test_gitignored_path_aborts_before_writing(self):
        self.write(".gitignore", "ignored.txt\n")
        sh(self.work, "git", "add", ".gitignore")
        sh(self.work, "git", "commit", "-q", "-m", "ignore")
        rc, out = self.px("create", "ignored.txt", "x", "-m", "m")
        self.assertEqual(rc, 1)
        self.assertIn("gitignored", out)
        self.assertFalse(os.path.exists(os.path.join(self.work, "ignored.txt")))

    def test_commit_is_scoped_to_patched_files(self):
        self.write("other.txt", "o\n")
        sh(self.work, "git", "add", "other.txt")
        rc, out = self.px("replace", "seed.txt", "alpha", "ALPHA", "-m", "m")
        self.assertEqual(rc, 0, out)
        names = sh(self.work, "git", "show", "--name-only", "--format=",
                   "HEAD").stdout.split()
        self.assertEqual(names, ["seed.txt"])
        staged = sh(self.work, "git", "diff", "--cached", "--name-only").stdout.split()
        self.assertEqual(staged, ["other.txt"])


class TestEncoding(PatchxCase):
    def test_utf8_content_under_c_locale(self):
        dash = "\u2014"
        self.write("seed.txt", "alpha %s beta\n" % dash)
        sh(self.work, "git", "commit", "-q", "-am", "dash")
        sh(self.work, "git", "push", "-q")
        ops = {"message": "m", "ops": [
            {"op": "replace", "file": "seed.txt", "old": "alpha",
             "new": "ALPHA %s x" % dash}]}
        ops_file = os.path.join(self.tmp, "ops.json")
        with open(ops_file, "w", encoding="utf-8") as f:
            json.dump(ops, f, ensure_ascii=False)
        env = dict(os.environ, LC_ALL="C", LANG="C", PYTHONUTF8="0",
                   PYTHONCOERCECLOCALE="0")
        rc, out = self.px("--file", ops_file, env=env)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.read("seed.txt"),
                         "ALPHA %s x %s beta\n" % (dash, dash))


if __name__ == "__main__":
    unittest.main(verbosity=2)
