from __future__ import annotations

import os
import sys
from collections.abc import Callable

from app.projects.manifest import ResourceLimits

_BYTES_PER_MEGABYTE: int = 1024 * 1024


def build_process_hardening_hook(limits: ResourceLimits | None) -> Callable[[], None] | None:
    if sys.platform == "win32":
        return None

    import resource

    requested_limits: tuple[tuple[str, int], ...] = (
        ("RLIMIT_CORE", 0),
        *(
            (
                ("RLIMIT_FSIZE", limits.write_limit_megabytes * _BYTES_PER_MEGABYTE),
                ("RLIMIT_NOFILE", limits.open_files_max),
            )
            if limits is not None
            else ()
        ),
    )

    def harden_child_process() -> None:
        os.setsid()
        os.umask(0o077)
        for limit_name, requested_value in requested_limits:
            limit_constant = getattr(resource, limit_name, None)
            if limit_constant is None:
                continue
            try:
                _current_soft, current_hard = resource.getrlimit(limit_constant)
                enforced = (
                    requested_value
                    if current_hard == resource.RLIM_INFINITY
                    else min(requested_value, current_hard)
                )
                resource.setrlimit(limit_constant, (enforced, current_hard))
            except (OSError, ValueError):
                continue

    return harden_child_process
