from __future__ import annotations

import re
from typing import Final

PROJECT_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,46}[a-z0-9])?$")
ENVIRONMENT_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
GITHUB_REPOSITORY_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,38})/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})$"
)
GIT_REFERENCE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._/-]{0,127})$")
ACCOUNT_LABEL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9 _-]{0,30}[A-Za-z0-9])?$"
)

MANIFEST_FILENAME: Final[str] = "fleet.toml"
WORKSPACE_DIRECTORY_NAME: Final[str] = "workspace"
VIRTUALENV_DIRECTORY_NAME: Final[str] = "venv"
SCRATCH_DIRECTORY_NAME: Final[str] = "scratch"
LOG_DIRECTORY_NAME: Final[str] = "logs"

SANDBOX_WORKSPACE_MOUNT: Final[str] = "/workspace"
SANDBOX_VIRTUALENV_MOUNT: Final[str] = "/opt/venv"
SANDBOX_SCRATCH_MOUNT: Final[str] = "/tmp"

FORBIDDEN_WORKSPACE_FILENAMES: Final[frozenset[str]] = frozenset({".env", ".git", ".netrc", ".npmrc", ".ssh"})

CRASH_BACKOFF_SECONDS: Final[tuple[int, ...]] = (5, 10, 30, 60, 120)
GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS: Final[float] = 8.0
RESOURCE_SAMPLING_INTERVAL_SECONDS: Final[float] = 5.0
CRASH_COUNTER_RESET_THRESHOLD_SECONDS: Final[float] = 60.0
DISK_USAGE_SAMPLE_EVERY_N_TICKS: Final[int] = 6
CHILD_LOG_LINE_MAX_BYTES: Final[int] = 8192
CHILD_LOG_RETAINED_LINES: Final[int] = 200

BUILD_TIMEOUT_CEILING_SECONDS: Final[int] = 3600
BUILD_STEP_OUTPUT_RETAINED_BYTES: Final[int] = 16384

ARCHIVE_MAX_COMPRESSED_BYTES: Final[int] = 32 * 1024 * 1024
ARCHIVE_MAX_UNCOMPRESSED_BYTES: Final[int] = 512 * 1024 * 1024
ARCHIVE_MAX_ENTRY_BYTES: Final[int] = 64 * 1024 * 1024
ARCHIVE_MAX_ENTRY_COUNT: Final[int] = 8192
ARCHIVE_MAX_PATH_DEPTH: Final[int] = 24
ARCHIVE_MAX_COMPRESSION_RATIO: Final[int] = 200
ARCHIVE_CHUNK_BYTES: Final[int] = 1 << 20

CLONE_TIMEOUT_SECONDS: Final[int] = 300
CLONE_MAX_WORKSPACE_BYTES: Final[int] = 512 * 1024 * 1024

DEFAULT_MEMORY_LIMIT_MEGABYTES: Final[int] = 512
DEFAULT_PROCESS_LIMIT: Final[int] = 128
DEFAULT_OPEN_FILE_LIMIT: Final[int] = 1024
DEFAULT_WRITE_LIMIT_MEGABYTES: Final[int] = 256
DEFAULT_CPU_QUOTA: Final[float] = 1.0

MEMORY_LIMIT_CEILING_MEGABYTES: Final[int] = 32768
PROCESS_LIMIT_CEILING: Final[int] = 4096
OPEN_FILE_LIMIT_CEILING: Final[int] = 65536
WRITE_LIMIT_CEILING_MEGABYTES: Final[int] = 65536
CPU_QUOTA_CEILING: Final[float] = 64.0

PROJECT_LIST_PAGE_SIZE: Final[int] = 6
DASHBOARD_PROCESS_PAGE_SIZE: Final[int] = 5
ALERT_RULE_PAGE_SIZE: Final[int] = 8
EVENT_HISTORY_PAGE_SIZE: Final[int] = 8
SECRET_LIST_PAGE_SIZE: Final[int] = 10

ALERT_QUEUE_CAPACITY: Final[int] = 2048
ALERT_DEFAULT_THROTTLE_SECONDS: Final[int] = 120
EVENT_RETENTION_LIMIT: Final[int] = 5000
