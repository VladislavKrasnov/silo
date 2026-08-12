from __future__ import annotations

from typing import Final

BLOCKED_ENVIRONMENT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "BASH_ENV",
        "ENV",
        "GIT_ASKPASS",
        "GIT_SSH_COMMAND",
        "HOME",
        "IFS",
        "LD_AUDIT",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "NODE_OPTIONS",
        "PATH",
        "PERL5LIB",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONWARNINGS",
        "RUBYOPT",
        "SHELL",
        "TMPDIR",
        "VIRTUAL_ENV",
    }
)


def build_base_environment(
    *, virtualenv_root: str, virtualenv_bin: str, home_directory: str, project_slug: str
) -> dict[str, str]:
    return {
        "PATH": f"{virtualenv_bin}:/usr/local/bin:/usr/bin:/bin",
        "HOME": home_directory,
        "TMPDIR": home_directory,
        "VIRTUAL_ENV": virtualenv_root,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "PIP_NO_PROGRESS_BAR": "1",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        # Limit OpenBLAS / OpenMP thread pools.  Without these, each worker
        # thread allocates its own memory arenas, multiplying RSS by the CPU
        # count.  Single-threaded BLAS is slower but fits in the memory budget
        # of a shared container.
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        # Limit glibc's per-thread malloc arena count (default = 8× CPUs).
        # Each arena can hold megabytes of fragmented free space; capping at 2
        # dramatically reduces virtual-address bloat for Python processes.
        "MALLOC_ARENA_MAX": "2",
        "PROJECT_SLUG": project_slug,
    }


def sanitize_project_environment(candidate_environment: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in candidate_environment.items()
        if key not in BLOCKED_ENVIRONMENT_KEYS and not key.startswith("LD_")
    }
