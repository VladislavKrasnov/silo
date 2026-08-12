from __future__ import annotations

import os

import psutil

_CGROUP_V1_MEMORY_USAGE_PATH: str = "/sys/fs/cgroup/memory/memory.usage_in_bytes"
_CGROUP_V1_MEMORY_LIMIT_PATH: str = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
_CGROUP_V1_MEMSW_USAGE_PATH: str = "/sys/fs/cgroup/memory/memory.memsw.usage_in_bytes"
_CGROUP_V1_MEMSW_LIMIT_PATH: str = "/sys/fs/cgroup/memory/memory.memsw.limit_in_bytes"
_CGROUP_V2_MEMORY_CURRENT_PATH: str = "/sys/fs/cgroup/memory.current"
_CGROUP_V2_MEMORY_MAX_PATH: str = "/sys/fs/cgroup/memory.max"
_CGROUP_V2_SWAP_CURRENT_PATH: str = "/sys/fs/cgroup/memory.swap.current"
_CGROUP_V2_SWAP_MAX_PATH: str = "/sys/fs/cgroup/memory.swap.max"

_BYTE_UNIT_SUFFIXES: tuple[str, ...] = ("b", "kb", "mb", "gb", "tb")


def read_cgroup_metric(candidate_paths: tuple[str, ...], fallback_value: int) -> int:
    for path in candidate_paths:
        try:
            raw_content = open(path).read().strip()
        except OSError:
            continue
        if raw_content == "max":
            return fallback_value
        try:
            return int(raw_content)
        except ValueError:
            continue
    return fallback_value


def collect_host_memory_snapshot() -> tuple[int, int, int, int]:
    system_memory = psutil.virtual_memory()
    system_swap = psutil.swap_memory()

    memory_used = read_cgroup_metric(
        (_CGROUP_V1_MEMORY_USAGE_PATH, _CGROUP_V2_MEMORY_CURRENT_PATH), system_memory.used
    )
    memory_total = read_cgroup_metric(
        (_CGROUP_V1_MEMORY_LIMIT_PATH, _CGROUP_V2_MEMORY_MAX_PATH), system_memory.total
    )
    if memory_total > system_memory.total:
        memory_total = system_memory.total

    memsw_used = read_cgroup_metric((_CGROUP_V1_MEMSW_USAGE_PATH,), 0)
    memsw_total = read_cgroup_metric((_CGROUP_V1_MEMSW_LIMIT_PATH,), 0)

    if memsw_total > 0:
        swap_used = max(0, memsw_used - memory_used)
        swap_total = max(0, memsw_total - memory_total)
    else:
        swap_used = read_cgroup_metric((_CGROUP_V2_SWAP_CURRENT_PATH,), 0)
        swap_total = read_cgroup_metric((_CGROUP_V2_SWAP_MAX_PATH,), 0)

    if swap_total > system_swap.total or swap_total == 0:
        swap_total = swap_used

    return memory_used, memory_total, swap_used, swap_total


def format_byte_count(byte_count: float) -> str:
    magnitude = float(byte_count)
    for unit_suffix in _BYTE_UNIT_SUFFIXES:
        if magnitude < 1024.0:
            return f"{int(magnitude)}{unit_suffix}"
        magnitude /= 1024.0
    return f"{int(magnitude)}pb"


def compute_directory_size(directory_path: str) -> int:
    total_size = 0
    try:
        for current_dir, _subdirs, file_names in os.walk(directory_path):
            for file_name in file_names:
                file_path = os.path.join(current_dir, file_name)
                if not os.path.islink(file_path):
                    try:
                        total_size += os.path.getsize(file_path)
                    except OSError:
                        continue
    except OSError:
        pass
    return total_size
