from __future__ import annotations

import datetime as dt
import html

from app.alerts.dispatcher import SEVERITY_LABELS, Alert
from app.alerts.kinds import ALERT_DEFINITIONS_BY_KIND
from app.alerts.settings import AlertPreferences, AlertRule
from app.database.repositories import EventRecord, GitHubAccountRecord, ProjectRecord
from app.i18n import translate
from app.pagination import Page
from app.reporting import ProjectSnapshot, SystemSnapshot
from app.system_stats import format_byte_count


def mono(value: object) -> str:
    return f"<code>{html.escape(str(value))}</code>"


def bold(value: object) -> str:
    return f"<b>{html.escape(str(value))}</b>"


def format_duration(total_seconds: int) -> str:
    return str(dt.timedelta(seconds=max(0, total_seconds)))


def format_timestamp(epoch_seconds: float) -> str:
    return dt.datetime.fromtimestamp(epoch_seconds, dt.UTC).strftime("%Y-%m-%d %H:%M:%S")


def render_status_lines(snapshot: SystemSnapshot, lang: str) -> list[str]:
    return [
        f"{translate('dashboard.uptime', lang)}: {mono(format_duration(snapshot.uptime_seconds))}",
        f"{translate('dashboard.cpu', lang)}: {mono(f'{int(snapshot.cpu_percent)}%')}",
        f"{translate('dashboard.ram', lang)}: {mono(format_byte_count(snapshot.memory_used_bytes))}"
        f" / {mono(format_byte_count(snapshot.memory_total_bytes))}",
        f"{translate('dashboard.swap', lang)}: {mono(format_byte_count(snapshot.swap_used_bytes))}",
        f"{translate('dashboard.projects_storage', lang)}: "
        f"{mono(format_byte_count(snapshot.disk_used_bytes))}",
        f"{translate('dashboard.host_disk', lang)}: {mono(f'{int(snapshot.disk_percent)}%')}",
        f"{translate('dashboard.isolation', lang)}: {mono(snapshot.isolation_backend)}",
    ]


def render_dashboard(
    snapshot: SystemSnapshot, page: Page[ProjectSnapshot], total_projects: int, lang: str
) -> str:
    lines = [bold(translate("dashboard.title", lang)), "", *render_status_lines(snapshot, lang)]

    if total_projects == 0:
        lines += ["", translate("dashboard.no_projects", lang)]
        return "\n".join(lines)

    lines += [
        "",
        translate("dashboard.page_header", lang, page=page.page_index + 1, total=page.total_pages),
    ]

    for project in page.items:
        lines.append("")
        lines.append(f"{mono(project.slug)} — {mono(project.state)}")
        if project.pid is not None:
            lines.append(
                "  "
                + translate(
                    "dashboard.project_line",
                    lang,
                    pid=project.pid,
                    cpu=int(project.cpu_percent),
                    ram=format_byte_count(project.memory_bytes),
                    uptime=format_duration(project.uptime_seconds),
                )
            )
        if project.restart_count:
            lines.append("  " + translate("dashboard.restarts", lang, count=project.restart_count))

    return "\n".join(lines)


def render_project_list(title: str, page: Page[str], empty_message: str, lang: str) -> str:
    if not page.items:
        return f"{bold(title)}\n\n{empty_message}"
    page_marker = translate("common.page_marker", lang, page=page.page_index + 1, total=page.total_pages)
    return f"{bold(title)} — {page_marker}\n\n{translate('common.select_project', lang)}"


def render_project_detail(
    record: ProjectRecord, snapshot: ProjectSnapshot, secret_names: list[str], failure_detail: str, lang: str
) -> str:
    lines = [
        f"{bold(translate('projects.detail_title', lang))} {mono(record.slug)}",
        "",
        f"{translate('projects.state', lang)}: {mono(snapshot.state)}",
        f"{translate('projects.source', lang)}: {mono(record.source_kind)} {mono(record.source_reference)}",
    ]
    if record.git_reference:
        lines.append(f"{translate('projects.reference', lang)}: {mono(record.git_reference)}")
    autostart_word = translate("projects.on", lang) if record.autostart else translate("projects.off", lang)
    lines.append(f"{translate('projects.autostart_label', lang)}: {mono(autostart_word)}")
    lines.append(f"{translate('projects.added', lang)}: {mono(format_timestamp(record.created_at))}")

    if snapshot.pid is not None:
        lines += [
            "",
            f"pid {mono(snapshot.pid)}  cpu {mono(f'{int(snapshot.cpu_percent)}%')}  "
            f"ram {mono(format_byte_count(snapshot.memory_bytes))}",
            f"{translate('projects.uptime', lang)}: {mono(format_duration(snapshot.uptime_seconds))}",
        ]

    lines.append(f"{translate('projects.restarts', lang)}: {mono(snapshot.restart_count)}")
    lines.append(
        f"{translate('projects.variables_loaded', lang)}: {mono(len(secret_names))}"
        + (f" ({', '.join(mono(name) for name in secret_names[:8])})" if secret_names else "")
    )

    if failure_detail:
        lines += ["", f"{translate('projects.last_failure', lang)}: {mono(failure_detail[:200])}"]

    return "\n".join(lines)


def render_action_result(verb: str, slug: str) -> str:
    return f"{verb} {mono(slug)}."


def render_alert(alert: Alert) -> str:
    scope = f" {mono(alert.project_slug)}" if alert.project_slug else ""
    escaped_message = html.escape(alert.message)
    body = f"<pre>{escaped_message}</pre>" if "\n" in alert.message else escaped_message
    return (
        f"{bold(SEVERITY_LABELS.get(alert.severity, alert.severity.upper()))} — {alert.title}{scope}\n"
        f"{body}\n"
        f"{mono(format_timestamp(alert.created_at))}"
    )


def render_alert_rules(page: Page[str], rules: dict[str, AlertRule], lang: str) -> str:
    lines = [
        bold(translate("alerts.title", lang)),
        "",
        translate("alerts.page_hint", lang, page=page.page_index + 1, total=page.total_pages),
        "",
    ]
    for kind in page.items:
        definition = ALERT_DEFINITIONS_BY_KIND[kind]
        rule = rules.get(kind, AlertRule(enabled=True, throttle_seconds=0))
        state_word = translate("alerts.on", lang) if rule.enabled else translate("alerts.off", lang)
        throttle = (
            translate("alerts.throttle", lang, seconds=rule.throttle_seconds) if rule.throttle_seconds else ""
        )
        lines.append(f"{mono(state_word)} {definition.title} — {mono(definition.severity)}{throttle}")
    return "\n".join(lines)


def render_preferences(preferences: AlertPreferences, lang: str) -> str:
    quiet_window = (
        f"{preferences.quiet_hours_start:02d}:00-{preferences.quiet_hours_end:02d}:00 UTC"
        if preferences.quiet_hours_enabled
        else translate("thresholds.quiet_hours_disabled", lang)
    )
    return "\n".join(
        [
            bold(translate("thresholds.title", lang)),
            "",
            f"{translate('thresholds.cpu', lang)}: {mono(f'{preferences.cpu_threshold_percent}%')}",
            f"{translate('thresholds.memory', lang)}: {mono(f'{preferences.memory_threshold_percent}%')}",
            f"{translate('thresholds.disk', lang)}: {mono(f'{preferences.disk_threshold_percent}%')}",
            f"{translate('thresholds.minimum_severity', lang)}: {mono(preferences.minimum_severity)}",
            f"{translate('thresholds.quiet_hours', lang)}: {mono(quiet_window)}",
            "",
            translate("thresholds.quiet_hours_note", lang),
        ]
    )


def render_accounts(accounts: list[GitHubAccountRecord], lang: str) -> str:
    if not accounts:
        return f"{bold(translate('accounts.title', lang))}\n\n{translate('accounts.none', lang)}"
    lines = [bold(translate("accounts.title", lang)), ""]
    for account in accounts:
        added = translate("accounts.added_on", lang, date=format_timestamp(account.created_at))
        lines.append(f"{mono(account.label)} — {mono(account.username)} ({added})")
    return "\n".join(lines)


def _group_consecutive_events(events: tuple[EventRecord, ...]) -> list[tuple[EventRecord, int]]:
    groups: list[tuple[EventRecord, int]] = []
    for event in events:
        if groups:
            last_event, count = groups[-1]
            if (
                event.kind == last_event.kind
                and event.severity == last_event.severity
                and event.project_slug == last_event.project_slug
                and event.message == last_event.message
            ):
                groups[-1] = (last_event, count + 1)
                continue
        groups.append((event, 1))
    return groups


def render_events(page: Page[EventRecord], lang: str) -> str:
    if not page.items:
        return f"{bold(translate('events.title', lang))}\n\n{translate('events.empty', lang)}"
    lines = [
        bold(translate("events.title", lang)),
        "",
        translate("events.page_header", lang, page=page.page_index + 1, total=page.total_pages),
        "",
    ]
    for event, count in _group_consecutive_events(page.items):
        scope = f" {mono(event.project_slug)}" if event.project_slug else ""
        multiplier = f" {mono(f'{count}x')}" if count > 1 else ""
        lines.append(
            f"{mono(format_timestamp(event.created_at))} "
            f"{mono(SEVERITY_LABELS.get(event.severity, event.severity))}{scope}{multiplier}\n"
            f"  {html.escape(event.message[:200])}"
        )
    return "\n".join(lines)


def render_logs(slug: str, lines: list[str], lang: str) -> str:
    if not lines:
        return f"{bold(translate('logs.title', lang))} {mono(slug)}\n\n{translate('logs.empty', lang)}"
    body = html.escape("\n".join(lines)[-3000:])
    return f"{bold(translate('logs.title', lang))} {mono(slug)}\n\n<pre>{body}</pre>"


def render_secrets_overview(slug: str, names: list[str], lang: str) -> str:
    lines = [
        f"{bold(translate('secrets.title', lang))} {mono(slug)}",
        "",
        translate("secrets.explanation", lang),
        "",
    ]
    if not names:
        lines.append(translate("secrets.none_loaded", lang))
    else:
        lines.append(translate("secrets.loaded_count", lang, count=len(names)))
        lines += [f"  {mono(name)}" for name in names]
    return "\n".join(lines)
