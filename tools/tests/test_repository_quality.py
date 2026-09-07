from __future__ import annotations

import contextlib
import importlib.metadata
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.repository_quality import (
    EXPECTED_TOOL_VERSIONS,
    MAX_SELECTED_FILES,
    QualitySelectionError,
    main,
    run_quality,
    select_changed_python_paths,
    select_explicit_paths,
    select_working_tree_python_paths,
)


class RepositoryQualityTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "pyproject.toml").write_text("[tool.black]\n", encoding="utf-8")
        (self.root / "pkg").mkdir()
        (self.root / "pkg" / "one.py").write_text("value = 1\n", encoding="utf-8")
        (self.root / "pkg" / "two.py").write_text("value = 2\n", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def versions(self, tool):
        return EXPECTED_TOOL_VERSIONS[tool]

    def test_explicit_selection_is_sorted_deduplicated_and_fail_closed(self):
        self.assertEqual(
            select_explicit_paths(
                self.root, ["pkg/two.py", ".\\pkg\\one.py", "pkg/one.py"]
            ),
            ("pkg/one.py", "pkg/two.py"),
        )
        for path in (
            "pkg/missing.py",
            "pkg/readme.md",
            "../outside.py",
            "/absolute.py",
            "C:\\outside.py",
            "pkg/bad\nname.py",
            "pkg//one.py",
        ):
            with self.subTest(path=path), self.assertRaises(QualitySelectionError):
                select_explicit_paths(self.root, [path])

    def test_changed_selection_is_nul_safe_and_excludes_deleted_paths(self):
        completed = subprocess.CompletedProcess(
            [], 0, stdout=b"pkg/two.py\0docs/note.md\0pkg/one.py\0"
        )
        runner = Mock(return_value=completed)
        selected = select_changed_python_paths(
            self.root, "a" * 40, "b" * 40, merge_base=True, runner=runner
        )
        self.assertEqual(selected, ("pkg/one.py", "pkg/two.py"))
        command = runner.call_args.args[0]
        self.assertIn("-z", command)
        self.assertIn("--diff-filter=ACMRTUXB", command)
        self.assertIn("--no-renames", command)
        self.assertIn("--merge-base", command)
        self.assertFalse(runner.call_args.kwargs["shell"])
        self.assertEqual(runner.call_args.kwargs["timeout"], 20)

    def test_changed_selected_python_file_must_exist(self):
        completed = subprocess.CompletedProcess([], 0, stdout=b"pkg/deleted.py\0")
        with self.assertRaises(QualitySelectionError):
            select_changed_python_paths(
                self.root,
                "a" * 40,
                "b" * 40,
                runner=Mock(return_value=completed),
            )

    def test_git_selection_timeout_and_file_count_fail_closed(self):
        with self.assertRaises(QualitySelectionError):
            select_changed_python_paths(
                self.root,
                "a" * 40,
                "b" * 40,
                runner=Mock(side_effect=subprocess.TimeoutExpired(["git"], 20)),
            )
        oversized = b"".join(
            f"pkg/file-{index}.py\0".encode() for index in range(MAX_SELECTED_FILES + 1)
        )
        with self.assertRaises(QualitySelectionError):
            select_changed_python_paths(
                self.root,
                "a" * 40,
                "b" * 40,
                runner=Mock(
                    return_value=subprocess.CompletedProcess([], 0, stdout=oversized)
                ),
            )

    def test_check_uses_isolated_argv_per_tool_and_file_without_source_output(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
        failures = run_quality(
            self.root,
            ("pkg/one.py", "pkg/two.py"),
            mode="check",
            timeout_seconds=7,
            runner=runner,
            version_lookup=self.versions,
            executable="python-safe",
        )
        self.assertEqual(failures, ())
        self.assertEqual(runner.call_count, 4)
        for call in runner.call_args_list:
            command = call.args[0]
            self.assertEqual(command[:3], ["python-safe", "-I", "-m"])
            self.assertIn("--", command)
            self.assertTrue(command[-1].endswith(".py"))
            self.assertFalse(call.kwargs["shell"])
            self.assertEqual(call.kwargs["timeout"], 7)
            self.assertEqual(call.kwargs["stdout"], subprocess.PIPE)
            self.assertEqual(call.kwargs["stderr"], subprocess.PIPE)

    def test_timeout_and_nonzero_are_sanitized_and_do_not_skip_other_files(self):
        responses = [
            subprocess.TimeoutExpired(["tool"], 1, output=b"private source"),
            subprocess.CompletedProcess([], 1, b"private diff", b"private source"),
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 2, b"private diff", b"private source"),
        ]

        def runner(*_args, **_kwargs):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        failures = run_quality(
            self.root,
            ("pkg/one.py", "pkg/two.py"),
            mode="check",
            runner=runner,
            version_lookup=self.versions,
        )
        self.assertEqual(
            [(failure.kind, failure.tool, failure.path) for failure in failures],
            [
                ("timeout", "isort", "pkg/one.py"),
                ("formatting required", "black", "pkg/one.py"),
                ("subprocess failure", "black", "pkg/two.py"),
            ],
        )
        self.assertNotIn("private", repr(failures))
        self.assertEqual(responses, [])

    def test_missing_and_wrong_versions_are_distinct_and_run_no_file(self):
        runner = Mock()

        def versions(tool):
            if tool == "isort":
                raise importlib.metadata.PackageNotFoundError(tool)
            return "0.0"

        failures = run_quality(
            self.root,
            ("pkg/one.py",),
            mode="check",
            runner=runner,
            version_lookup=versions,
        )
        self.assertEqual(
            [(failure.kind, failure.tool) for failure in failures],
            [("missing tool", "isort"), ("wrong tool version", "black")],
        )
        runner.assert_not_called()

    def test_timeout_bound_is_enforced(self):
        for timeout in (0, 121):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                run_quality(
                    self.root,
                    ("pkg/one.py",),
                    mode="check",
                    timeout_seconds=timeout,
                    version_lookup=self.versions,
                )

    def test_black_cache_is_ephemeral_and_parent_environment_unchanged(self):
        observed = []

        def runner(command, **kwargs):
            if command[3] == "black":
                cache = Path(kwargs["env"]["BLACK_CACHE_DIR"])
                self.assertTrue(cache.is_dir())
                self.assertNotEqual(str(cache), "fictional-old-cache")
                observed.append(cache)
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with patch.dict("os.environ", {"BLACK_CACHE_DIR": "fictional-old-cache"}):
            import os

            self.assertEqual(
                run_quality(
                    self.root,
                    ("pkg/one.py",),
                    mode="check",
                    runner=runner,
                    version_lookup=self.versions,
                ),
                (),
            )
            self.assertEqual(os.environ["BLACK_CACHE_DIR"], "fictional-old-cache")
        self.assertEqual(len(observed), 1)
        self.assertFalse(observed[0].exists())

    def test_quality_cli_failure_has_fixed_guidance_not_raw_process_output(self):
        from tools.repository_quality import QualityFailure

        output = io.StringIO()
        with patch("tools.repository_quality.ROOT", self.root):
            with patch(
                "tools.repository_quality.run_quality",
                return_value=(QualityFailure("timeout", "black", "pkg/one.py"),),
            ):
                with contextlib.redirect_stderr(output):
                    self.assertEqual(main(["check", "--paths", "pkg/one.py"]), 1)
        self.assertIn("source_mutation=none", output.getvalue())
        self.assertIn("next_action=inspect_local_tool_environment", output.getvalue())

    def test_cache_cleanup_after_black_timeout_does_not_retry(self):
        observed = []

        def runner(command, **kwargs):
            if command[3] == "black":
                observed.append(Path(kwargs["env"]["BLACK_CACHE_DIR"]))
                raise subprocess.TimeoutExpired(command, 1, output=b"fictional-private")
            return subprocess.CompletedProcess(command, 0, b"", b"")

        failures = run_quality(
            self.root,
            ("pkg/one.py",),
            mode="check",
            runner=runner,
            version_lookup=self.versions,
        )
        self.assertEqual(len(observed), 1)
        self.assertFalse(observed[0].exists())
        self.assertEqual(failures[0].kind, "timeout")
        self.assertNotIn("fictional-private", repr(failures))

    def test_format_failure_guidance_does_not_claim_no_source_changes(self):
        from tools.repository_quality import QualityFailure

        output = io.StringIO()
        with patch("tools.repository_quality.ROOT", self.root):
            with patch(
                "tools.repository_quality.run_quality",
                return_value=(
                    QualityFailure("subprocess failure", "black", "pkg/one.py"),
                ),
            ):
                with contextlib.redirect_stderr(output):
                    self.assertEqual(main(["format", "--paths", "pkg/one.py"]), 1)
        self.assertIn(
            "source_mutation=possible_partial_local_format", output.getvalue()
        )
        self.assertIn("next_action=diagnose_local_tool", output.getvalue())

    def test_working_tree_combines_tracked_and_untracked_without_duplicates(self):
        runner = Mock(
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=b"pkg/one.py\0"),
                subprocess.CompletedProcess([], 0, stdout=b"pkg/two.py\0pkg/one.py\0"),
            ]
        )
        self.assertEqual(
            select_working_tree_python_paths(self.root, runner=runner),
            ("pkg/one.py", "pkg/two.py"),
        )
        self.assertIn("HEAD", runner.call_args_list[0].args[0])
        self.assertIn("--exclude-standard", runner.call_args_list[1].args[0])

    def test_working_tree_git_error_is_not_an_empty_success(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 128, stdout=b""))
        with self.assertRaises(QualitySelectionError):
            select_working_tree_python_paths(self.root, runner=runner)

    def test_working_tree_cli_disallows_format_before_selection(self):
        with patch(
            "tools.repository_quality.select_working_tree_python_paths"
        ) as select:
            with (
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                main(["format", "--working-tree"])
            self.assertEqual(error.exception.code, 2)
            select.assert_not_called()

    def test_working_tree_empty_cli_skips_tools(self):
        with patch(
            "tools.repository_quality.select_working_tree_python_paths", return_value=()
        ):
            with patch("tools.repository_quality.run_quality") as run:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["check", "--working-tree"]), 0)
                run.assert_not_called()

    def test_real_git_working_tree_selects_disk_changes_not_index_snapshot(self):
        def git(*args):
            return subprocess.run(
                ["git", *args],
                cwd=self.root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )

        git("init")
        git("config", "user.name", "Fictional Quality Test")
        git("config", "user.email", "quality@example.invalid")
        git("config", "commit.gpgsign", "false")
        git("config", "core.hooksPath", str(self.root / "no-hooks"))
        for name in ("deleted.py", "renamed.py", "cancelled.py"):
            (self.root / "pkg" / name).write_text("value = 1\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "fictional baseline")
        self.assertEqual(select_working_tree_python_paths(self.root), ())
        (self.root / "pkg/one.py").write_text("value = 3\n", encoding="utf-8")
        git("add", "pkg/one.py")
        (self.root / "pkg/two.py").write_text("value = 4\n", encoding="utf-8")
        (self.root / "pkg/new file.py").write_text("value = 5\n", encoding="utf-8")
        (self.root / "ignored.py").write_text("value = 6\n", encoding="utf-8")
        (self.root / "pkg/deleted.py").unlink()
        git("mv", "pkg/renamed.py", "pkg/moved.py")
        (self.root / "pkg/cancelled.py").write_text("value = 2\n", encoding="utf-8")
        git("add", "pkg/cancelled.py")
        (self.root / "pkg/cancelled.py").write_text("value = 1\n", encoding="utf-8")
        self.assertEqual(
            select_working_tree_python_paths(self.root),
            ("pkg/moved.py", "pkg/new file.py", "pkg/one.py", "pkg/two.py"),
        )


if __name__ == "__main__":
    unittest.main()
