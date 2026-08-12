from __future__ import annotations

from pathlib import Path

from app.system_stats import compute_directory_size, format_byte_count, read_cgroup_metric


class TestFormatByteCount:
    def test_bytes_stay_under_kilobyte(self) -> None:
        assert format_byte_count(512) == "512b"

    def test_scales_through_units(self) -> None:
        assert format_byte_count(1024) == "1kb"
        assert format_byte_count(1024 * 1024) == "1mb"
        assert format_byte_count(1024 * 1024 * 1024) == "1gb"

    def test_truncates_rather_than_rounds(self) -> None:
        assert format_byte_count(1024 * 1.9) == "1kb"


class TestReadCgroupMetric:
    def test_returns_fallback_when_no_path_exists(self) -> None:
        assert read_cgroup_metric(("/nonexistent/path/one", "/nonexistent/path/two"), 42) == 42

    def test_reads_integer_value_from_first_readable_path(self, tmp_path: Path) -> None:
        metric_file = tmp_path / "usage_in_bytes"
        metric_file.write_text("2048\n")
        assert read_cgroup_metric((str(metric_file),), 0) == 2048

    def test_max_sentinel_falls_back(self, tmp_path: Path) -> None:
        metric_file = tmp_path / "memory.max"
        metric_file.write_text("max\n")
        assert read_cgroup_metric((str(metric_file),), 999) == 999


class TestComputeDirectorySize:
    def test_sums_file_sizes_recursively(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_bytes(b"x" * 10)
        nested = tmp_path / "nested"
        nested.mkdir()
        (nested / "b.txt").write_bytes(b"y" * 20)

        assert compute_directory_size(str(tmp_path)) == 30

    def test_missing_directory_returns_zero(self) -> None:
        assert compute_directory_size("/definitely/not/a/real/path") == 0
