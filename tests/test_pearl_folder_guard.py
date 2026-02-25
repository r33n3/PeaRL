"""Tests for .pearl folder protection guard."""

from pearl_dev.pearl_folder_guard import is_pearl_destructive_bash, is_pearl_write_target


class TestDestructiveBashDetection:
    """Test detection of destructive bash commands targeting .pearl."""

    def test_rm_rf_pearl(self):
        assert is_pearl_destructive_bash("rm -rf .pearl") is True

    def test_rm_r_pearl_trailing_slash(self):
        assert is_pearl_destructive_bash("rm -r .pearl/") is True

    def test_rm_pearl_file(self):
        assert is_pearl_destructive_bash("rm .pearl/audit.jsonl") is True

    def test_rmdir_pearl(self):
        assert is_pearl_destructive_bash("rmdir .pearl") is True

    def test_remove_item_windows(self):
        assert is_pearl_destructive_bash("Remove-Item -Recurse .pearl") is True

    def test_del_pearl_windows(self):
        assert is_pearl_destructive_bash("del /s .pearl\\audit.jsonl") is True

    def test_rd_pearl_windows(self):
        assert is_pearl_destructive_bash("rd /s /q .pearl") is True

    def test_shutil_rmtree(self):
        assert is_pearl_destructive_bash(
            'python -c "import shutil; shutil.rmtree(\'.pearl\')"'
        ) is True

    def test_mv_pearl_away(self):
        assert is_pearl_destructive_bash("mv .pearl /tmp/backup") is True

    def test_move_item_windows(self):
        assert is_pearl_destructive_bash("Move-Item .pearl C:\\temp") is True

    def test_rm_rf_dot_nuke(self):
        assert is_pearl_destructive_bash("rm -rf .") is True

    def test_rm_rf_star_nuke(self):
        assert is_pearl_destructive_bash("rm -rf *") is True


class TestSafeBashCommands:
    """Test that safe commands are NOT blocked."""

    def test_cat_pearl_file(self):
        assert is_pearl_destructive_bash("cat .pearl/audit.jsonl") is False

    def test_ls_pearl(self):
        assert is_pearl_destructive_bash("ls -la .pearl/") is False

    def test_head_pearl_file(self):
        assert is_pearl_destructive_bash("head -20 .pearl/cost-ledger.jsonl") is False

    def test_tail_pearl_file(self):
        assert is_pearl_destructive_bash("tail -f .pearl/audit.jsonl") is False

    def test_rm_unrelated_directory(self):
        assert is_pearl_destructive_bash("rm -rf dist/") is False

    def test_rm_unrelated_file(self):
        assert is_pearl_destructive_bash("rm temp.txt") is False

    def test_git_commands(self):
        assert is_pearl_destructive_bash("git add .pearl/") is False

    def test_python_run(self):
        assert is_pearl_destructive_bash("python -m pytest") is False

    def test_pearl_dev_sync(self):
        assert is_pearl_destructive_bash("pearl-dev sync") is False


class TestWriteTargetDetection:
    """Test detection of Write/Edit targets inside .pearl/."""

    def test_relative_pearl_path(self):
        assert is_pearl_write_target(".pearl/audit.jsonl") is True

    def test_absolute_unix_pearl_path(self):
        assert is_pearl_write_target("/home/user/project/.pearl/cost-ledger.jsonl") is True

    def test_absolute_windows_pearl_path(self):
        assert is_pearl_write_target("C:\\Users\\dev\\project\\.pearl\\audit.jsonl") is True

    def test_pearl_config_file(self):
        assert is_pearl_write_target(".pearl/pearl-dev.toml") is True

    def test_pearl_subdirectory(self):
        assert is_pearl_write_target(".pearl/approvals/req_001.json") is True

    def test_non_pearl_source_file(self):
        assert is_pearl_write_target("src/main.py") is False

    def test_pearl_dev_module(self):
        assert is_pearl_write_target("src/pearl_dev/hooks.py") is False

    def test_pearl_in_filename_not_dir(self):
        assert is_pearl_write_target("docs/pearl-guide.md") is False

    def test_empty_path(self):
        assert is_pearl_write_target("") is False
