from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

import psutil

from app.alerts.dispatcher import AlertDispatcher
from app.alerts.kinds import AlertKind
from app.alerts.settings import AlertSettingsStore
from app.constants import DISK_USAGE_SAMPLE_EVERY_N_TICKS, RESOURCE_SAMPLING_INTERVAL_SECONDS
from app.runtime.fleet import FleetManager
from app.runtime.supervisor import ProjectSupervisor
from app.system_stats import collect_host_memory_snapshot, compute_directory_size


@dataclass(frozen=True, slots=True)
class SystemSnapshot:
    uptime_seconds: int
    cpu_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    swap_used_bytes: int
    disk_used_bytes: int
    disk_percent: float
    isolation_backend: str


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    slug: str
    state: str
    pid: int | None
    cpu_percent: float
    memory_bytes: int
    uptime_seconds: int
    restart_count: int


def build_project_snapshot(supervisor: ProjectSupervisor) -> ProjectSnapshot:
    return ProjectSnapshot(
        slug=supervisor.slug,
        state=str(supervisor.state),
        pid=supervisor.pid,
        cpu_percent=supervisor.cpu_percent,
        memory_bytes=supervisor.memory_bytes(),
        uptime_seconds=int(time.time() - supervisor.start_time) if supervisor.pid is not None else 0,
        restart_count=supervisor.restart_count,
    )


class ResourceSampler:
    def __init__(
        self,
        fleet: FleetManager,
        projects_root_dir: Path,
        alerts: AlertDispatcher,
        settings: AlertSettingsStore,
        shutdown_event: asyncio.Event,
    ):
        self.fleet = fleet
        self.projects_root_dir = projects_root_dir
        self.alerts = alerts
        self.settings = settings
        self.shutdown_event = shutdown_event
        self.process_start_time = time.time()
        self.cpu_percent: float = 0.0
        self.disk_used_bytes: int = 0
        self.isolation_backend: str = "unknown"
        psutil.cpu_percent(interval=None)

    def build_system_snapshot(self) -> SystemSnapshot:
        memory_used, memory_total, swap_used, _swap_total = collect_host_memory_snapshot()
        try:
            disk_percent = psutil.disk_usage(str(self.projects_root_dir)).percent
        except OSError:
            disk_percent = 0.0

        return SystemSnapshot(
            uptime_seconds=int(time.time() - self.process_start_time),
            cpu_percent=self.cpu_percent,
            memory_used_bytes=memory_used,
            memory_total_bytes=memory_total,
            swap_used_bytes=swap_used,
            disk_used_bytes=self.disk_used_bytes,
            disk_percent=disk_percent,
            isolation_backend=self.isolation_backend,
        )

    def _evaluate_host_thresholds(self, snapshot: SystemSnapshot) -> None:
        preferences = self.settings.preferences
        pressures: list[str] = []

        if snapshot.cpu_percent >= preferences.cpu_threshold_percent:
            pressures.append(
                f"CPU at {int(snapshot.cpu_percent)}% (threshold {preferences.cpu_threshold_percent}%)"
            )

        if snapshot.memory_total_bytes > 0:
            memory_percent = 100.0 * snapshot.memory_used_bytes / snapshot.memory_total_bytes
            if memory_percent >= preferences.memory_threshold_percent:
                pressures.append(
                    f"memory at {int(memory_percent)}% (threshold {preferences.memory_threshold_percent}%)"
                )

        if snapshot.disk_percent >= preferences.disk_threshold_percent:
            pressures.append(
                f"disk at {int(snapshot.disk_percent)}% (threshold {preferences.disk_threshold_percent}%)"
            )

        if pressures:
            self.alerts.publish(AlertKind.HOST_RESOURCE_PRESSURE, "; ".join(pressures))

    async def run(self) -> None:
        tick_count = 0
        while not self.shutdown_event.is_set():
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=RESOURCE_SAMPLING_INTERVAL_SECONDS)
                return
            except TimeoutError:
                pass

            self.cpu_percent = psutil.cpu_percent(interval=None)
            self.fleet.sample_resource_usage()

            if tick_count % DISK_USAGE_SAMPLE_EVERY_N_TICKS == 0:
                self.disk_used_bytes = await asyncio.to_thread(
                    compute_directory_size, str(self.projects_root_dir)
                )
                self._evaluate_host_thresholds(self.build_system_snapshot())
            tick_count += 1
