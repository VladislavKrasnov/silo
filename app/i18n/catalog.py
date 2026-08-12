from __future__ import annotations

from typing import Final

STRINGS: Final[dict[str, dict[str, str]]] = {
    "language.pick_title": {"en": "Choose your language", "ru": "Выберите язык"},
    "language.button_en": {"en": "English", "ru": "English"},
    "language.button_ru": {"en": "Русский", "ru": "Русский"},
    "language.changed": {"en": "Language set to English.", "ru": "Язык переключён на русский."},
    "language.settings_row": {"en": "Language", "ru": "Язык"},
    "menu.title": {"en": "Fleet orchestrator", "ru": "Оркестратор ботов"},
    "menu.start_restart": {"en": "Start / Restart", "ru": "Запуск / Перезапуск"},
    "menu.stop": {"en": "Stop", "ru": "Стоп"},
    "menu.status": {"en": "Status", "ru": "Статус"},
    "menu.projects": {"en": "Projects", "ru": "Проекты"},
    "menu.settings": {"en": "Settings", "ru": "Настройки"},
    "menu.no_projects": {
        "en": "No projects installed yet. Open Projects to add one.",
        "ru": "Проекты ещё не установлены. Откройте раздел «Проекты», чтобы добавить.",
    },
    "menu.projects_running": {"en": "Running: {running} / {total}", "ru": "Запущено: {running} / {total}"},
    "dashboard.title": {"en": "Fleet status", "ru": "Статус оркестратора"},
    "dashboard.uptime": {"en": "Uptime", "ru": "Аптайм"},
    "dashboard.cpu": {"en": "CPU", "ru": "ЦП"},
    "dashboard.ram": {"en": "RAM", "ru": "ОЗУ"},
    "dashboard.swap": {"en": "Swap", "ru": "Подкачка"},
    "dashboard.projects_storage": {"en": "Projects storage", "ru": "Данные проектов"},
    "dashboard.host_disk": {"en": "Host disk used", "ru": "Занято на диске хоста"},
    "dashboard.isolation": {"en": "Isolation", "ru": "Изоляция"},
    "dashboard.no_projects": {
        "en": "No projects are registered. Open Projects to add one.",
        "ru": "Нет установленных проектов. Откройте «Проекты», чтобы добавить.",
    },
    "dashboard.page_header": {"en": "Projects — page {page}/{total}", "ru": "Проекты — стр. {page}/{total}"},
    "dashboard.project_line": {
        "en": "pid {pid}  cpu {cpu}%  ram {ram}  uptime {uptime}",
        "ru": "pid {pid}  цп {cpu}%  озу {ram}  аптайм {uptime}",
    },
    "dashboard.restarts": {"en": "restarts {count}", "ru": "перезапусков {count}"},
    "common.back": {"en": "Back", "ru": "Назад"},
    "common.prev": {"en": "Prev", "ru": "Назад"},
    "common.next": {"en": "Next", "ru": "Далее"},
    "common.refresh": {"en": "Refresh", "ru": "Обновить"},
    "common.cancel_hint": {"en": "Send /cancel to abort.", "ru": "Отправьте /cancel, чтобы отменить."},
    "common.select_project": {"en": "Select a project below.", "ru": "Выберите проект ниже."},
    "common.page_marker": {"en": "page {page}/{total}", "ru": "стр. {page}/{total}"},
    "projects.title": {"en": "Projects", "ru": "Проекты"},
    "projects.empty": {
        "en": "No projects are registered. Add one from GitHub or upload a zip archive.",
        "ru": "Нет установленных проектов. Добавьте проект из GitHub или загрузите zip-архив.",
    },
    "projects.add_github": {"en": "Add from GitHub", "ru": "Добавить из GitHub"},
    "projects.upload_zip": {"en": "Upload zip", "ru": "Загрузить zip"},
    "projects.action_start_title": {"en": "Start a project", "ru": "Запустить проект"},
    "projects.action_stop_title": {"en": "Stop a project", "ru": "Остановить проект"},
    "projects.action_restart_title": {"en": "Restart a project", "ru": "Перезапустить проект"},
    "projects.all_running": {
        "en": "Every registered project is already running.",
        "ru": "Все проекты уже запущены.",
    },
    "projects.none_running": {
        "en": "No projects are currently running.",
        "ru": "Сейчас нет запущенных проектов.",
    },
    "projects.verb_started": {"en": "Started", "ru": "Запущен"},
    "projects.verb_stopped": {"en": "Stopped", "ru": "Остановлен"},
    "projects.verb_restarted": {"en": "Restarted", "ru": "Перезапущен"},
    "projects.verb_rebuilding": {"en": "Rebuilding", "ru": "Пересобирается"},
    "projects.status_running": {"en": "Running", "ru": "Работает"},
    "projects.status_stopped": {"en": "Stopped", "ru": "Остановлен"},
    "projects.progress_start": {"en": "Starting {slug}…", "ru": "Запускаю {slug}…"},
    "projects.progress_stop": {"en": "Stopping {slug}…", "ru": "Останавливаю {slug}…"},
    "projects.progress_restart": {"en": "Restarting {slug}…", "ru": "Перезапускаю {slug}…"},
    "projects.progress_rebuild": {"en": "Rebuilding {slug}…", "ru": "Пересобираю {slug}…"},
    "projects.progress_pull": {
        "en": "Pulling the latest revision for {slug}…",
        "ru": "Загружаю обновления для {slug}…",
    },
    "projects.progress_delete": {"en": "Deleting {slug}…", "ru": "Удаляю {slug}…"},
    "projects.progress_stop_all": {"en": "Stopping every project…", "ru": "Останавливаю все проекты…"},
    "projects.progress_restart_all": {
        "en": "Restarting the whole fleet…",
        "ru": "Перезапускаю весь оркестратор…",
    },
    "projects.stop_all_button": {"en": "Stop everything", "ru": "Остановить всё"},
    "projects.restart_all_button": {"en": "Restart everything", "ru": "Перезапустить всё"},
    "projects.stop_all_confirm_title": {
        "en": "Stop every running project?",
        "ru": "Остановить все запущенные проекты?",
    },
    "projects.stop_all_confirm_body": {
        "en": "Every running project stops. Projects with autostart can be started again from their menu.",
        "ru": "Все запущенные проекты будут остановлены. Проекты с автозапуском можно снова "
        "запустить из их меню.",
    },
    "projects.restart_all_confirm_title": {
        "en": "Restart the whole fleet?",
        "ru": "Перезапустить весь оркестратор?",
    },
    "projects.restart_all_confirm_body": {
        "en": "Every running project restarts and every stopped project starts.",
        "ru": "Все запущенные проекты перезапустятся, а остановленные — запустятся.",
    },
    "projects.open_project": {"en": "Open project", "ru": "Открыть проект"},
    "projects.button_stop": {"en": "Stop", "ru": "Стоп"},
    "projects.button_start": {"en": "Start", "ru": "Старт"},
    "projects.button_restart": {"en": "Restart", "ru": "Рестарт"},
    "projects.button_rebuild": {"en": "Rebuild", "ru": "Пересборка"},
    "projects.button_variables": {"en": "Variables", "ru": "Переменные"},
    "projects.button_logs": {"en": "Logs", "ru": "Логи"},
    "projects.button_autostart": {"en": "Autostart", "ru": "Автозапуск"},
    "projects.button_pull": {"en": "Pull latest", "ru": "Обновить из GitHub"},
    "projects.button_delete": {"en": "Delete", "ru": "Удалить"},
    "projects.autostart_enabled": {"en": "Autostart enabled.", "ru": "Автозапуск включён."},
    "projects.autostart_disabled": {"en": "Autostart disabled.", "ru": "Автозапуск выключен."},
    "projects.detail_title": {"en": "Project", "ru": "Проект"},
    "projects.state": {"en": "State", "ru": "Состояние"},
    "projects.source": {"en": "Source", "ru": "Источник"},
    "projects.reference": {"en": "Reference", "ru": "Ветка/тег"},
    "projects.autostart_label": {"en": "Autostart", "ru": "Автозапуск"},
    "projects.on": {"en": "on", "ru": "вкл"},
    "projects.off": {"en": "off", "ru": "выкл"},
    "projects.added": {"en": "Added", "ru": "Добавлен"},
    "projects.uptime": {"en": "Uptime", "ru": "Аптайм"},
    "projects.restarts": {"en": "Restarts", "ru": "Перезапуски"},
    "projects.variables_loaded": {"en": "Variables loaded", "ru": "Загружено переменных"},
    "projects.last_failure": {"en": "Last failure", "ru": "Последняя ошибка"},
    "projects.no_longer_exists": {"en": "Project no longer exists.", "ru": "Проект больше не существует."},
    "projects.already_running": {"en": "{slug} is already running.", "ru": "{slug} уже запущен."},
    "projects.already_stopped": {"en": "{slug} is already stopped.", "ru": "{slug} уже остановлен."},
    "projects.already_running_alert": {"en": "Already running.", "ru": "Уже запущен."},
    "projects.already_stopped_alert": {"en": "Already stopped.", "ru": "Уже остановлен."},
    "projects.not_found": {"en": "No project named {slug} is registered.", "ru": "Проект {slug} не найден."},
    "projects.pulling": {"en": "Pulling the latest revision.", "ru": "Загружаю обновления из GitHub."},
    "projects.pull_failed": {"en": "Pull failed: {error}", "ru": "Не удалось обновить: {error}"},
    "projects.deleting": {"en": "Deleting.", "ru": "Удаляю."},
    "projects.delete_confirm_title": {
        "en": "Delete {slug} permanently?",
        "ru": "Удалить {slug} безвозвратно?",
    },
    "projects.delete_confirm_body": {
        "en": "Its workspace, virtual environment, logs and stored variables are all removed.",
        "ru": "Рабочая папка, окружение, логи и переменные будут удалены безвозвратно.",
    },
    "projects.confirm": {"en": "Confirm", "ru": "Подтвердить"},
    "projects.cancel_button": {"en": "Cancel", "ru": "Отмена"},
    "projects.installed": {"en": "Installed {slug}.", "ru": "Установлен {slug}."},
    "projects.files": {"en": "Files: {count}", "ru": "Файлов: {count}"},
    "projects.stripped": {
        "en": "Stripped: {links} links, {sensitive} sensitive paths",
        "ru": "Удалено: ссылок — {links}, чувствительных путей — {sensitive}",
    },
    "projects.manifest_generated": {
        "en": "A default fleet.toml was generated. Review it before starting the project.",
        "ru": "Сгенерирован файл fleet.toml по умолчанию. Проверьте его перед запуском.",
    },
    "projects.next_steps": {
        "en": "Load its environment variables, then start it from the project menu.",
        "ru": "Загрузите переменные окружения, затем запустите проект из его меню.",
    },
    "projects.install_failed": {"en": "Installation failed: {error}", "ru": "Установка не удалась: {error}"},
    "ingest.github_title": {"en": "Add from GitHub", "ru": "Добавить из GitHub"},
    "ingest.github_prompt": {
        "en": "Send the repository URL, optionally followed by a branch or tag.\nExample: {example}",
        "ru": "Отправьте адрес репозитория, при желании через пробел укажите ветку или тег.\n"
        "Пример: {example}",
    },
    "ingest.send_repo_url": {"en": "Send a repository URL.", "ru": "Отправьте адрес репозитория."},
    "ingest.rejected": {"en": "Rejected: {error}", "ru": "Отклонено: {error}"},
    "ingest.will_install_as": {
        "en": "Repository {repo} will be installed as {slug}.\n\nChoose the account to authenticate with.",
        "ru": "Репозиторий {repo} будет установлен как {slug}.\n\nВыберите аккаунт для авторизации.",
    },
    "ingest.public_no_account": {"en": "Public, no account", "ru": "Публичный, без аккаунта"},
    "ingest.cloning": {"en": "Cloning.", "ru": "Клонирую."},
    "ingest.cloning_progress": {
        "en": "Cloning the repository… this can take a few minutes.",
        "ru": "Клонирую репозиторий… это может занять несколько минут.",
    },
    "ingest.installing_progress": {"en": "Installing the archive…", "ru": "Устанавливаю архив…"},
    "ingest.zip_title": {"en": "Upload a zip archive", "ru": "Загрузка zip-архива"},
    "ingest.zip_prompt": {
        "en": "Send the archive as a document, up to {limit}.\nIt is validated in memory, never written to "
        "disk as an archive, and your upload is deleted from this chat once accepted.",
        "ru": "Отправьте архив как документ, размером до {limit}.\nОн проверяется в памяти, никогда не "
        "сохраняется на диск как архив, а ваше сообщение удаляется сразу после приёма.",
    },
    "ingest.zip_only": {"en": "Only zip archives are accepted.", "ru": "Принимаются только zip-архивы."},
    "ingest.zip_too_large": {
        "en": "Archive exceeds the {limit} limit.",
        "ru": "Архив превышает лимит {limit}.",
    },
    "secrets.catalog_hint": {
        "en": "Open a project and choose Variables.",
        "ru": "Откройте проект и выберите «Переменные».",
    },
    "secrets.title": {"en": "Environment variables", "ru": "Переменные окружения"},
    "secrets.explanation": {
        "en": "Values are encrypted at rest and injected straight into the process. "
        "They are never written to a file inside the project.",
        "ru": "Значения хранятся в зашифрованном виде и передаются напрямую процессу. "
        "Они никогда не записываются в файл внутри проекта.",
    },
    "secrets.none_loaded": {
        "en": "No variables are loaded for this project.",
        "ru": "Для этого проекта переменные не заданы.",
    },
    "secrets.loaded_count": {"en": "Loaded: {count}", "ru": "Загружено: {count}"},
    "secrets.button_load": {"en": "Load", "ru": "Загрузить"},
    "secrets.button_replace": {"en": "Replace all", "ru": "Заменить всё"},
    "secrets.button_purge": {"en": "Delete all", "ru": "Удалить всё"},
    "secrets.load_title": {"en": "Load variables for {slug}", "ru": "Загрузка переменных для {slug}"},
    "secrets.load_prompt": {
        "en": "Send the assignments as a message or upload a file. They will {mode}.\n"
        "Format: one KEY=value per line.\n\n"
        "Your message is deleted from this chat as soon as it is read, the values are "
        "encrypted at rest, and nothing is written into the project directory.",
        "ru": "Отправьте переменные сообщением или файлом. Они {mode}.\n"
        "Формат: одна пара KEY=value на строку.\n\n"
        "Ваше сообщение удаляется сразу после прочтения, значения хранятся в "
        "зашифрованном виде, ничего не записывается в папку проекта.",
    },
    "secrets.mode_merge": {"en": "merge into the stored set", "ru": "будут добавлены к уже сохранённым"},
    "secrets.mode_replace": {
        "en": "replace every stored variable",
        "ru": "заменят все сохранённые переменные",
    },
    "secrets.too_large": {"en": "The uploaded file is too large.", "ru": "Загруженный файл слишком большой."},
    "secrets.none_found": {
        "en": "No valid assignments were found.",
        "ru": "Не найдено ни одной корректной переменной.",
    },
    "secrets.stored_summary": {
        "en": "Stored {count} variable(s): {names}",
        "ru": "Сохранено переменных: {count} ({names})",
    },
    "secrets.ignored_lines": {
        "en": "Ignored {count} malformed line(s).",
        "ru": "Проигнорировано некорректных строк: {count}.",
    },
    "secrets.restart_hint": {
        "en": "Restart the project for the new values to take effect.",
        "ru": "Перезапустите проект, чтобы применить новые значения.",
    },
    "secrets.deleted_count": {"en": "Deleted {count} variable(s).", "ru": "Удалено переменных: {count}."},
    "settings.title": {"en": "Settings", "ru": "Настройки"},
    "settings.intro": {
        "en": "Configure which alerts are delivered, when they are suppressed, "
        "and which GitHub accounts are available for cloning private repositories.",
        "ru": "Настройте, какие уведомления приходят, когда они подавляются, "
        "и какие аккаунты GitHub доступны для клонирования приватных репозиториев.",
    },
    "settings.alert_rules": {"en": "Alert rules", "ru": "Уведомления"},
    "settings.thresholds": {"en": "Thresholds", "ru": "Пороги"},
    "settings.accounts": {"en": "GitHub accounts", "ru": "Аккаунты GitHub"},
    "settings.events": {"en": "Events", "ru": "События"},
    "settings.backup": {"en": "Backup", "ru": "Резервная копия"},
    "backup.progress": {
        "en": "Packing the project into an archive… this can take a moment.",
        "ru": "Собираю архив проекта… это может занять некоторое время.",
    },
    "backup.caption": {
        "en": "Backup ready — {count} files, {size}.\n.env and virtual environments are excluded.",
        "ru": "Резервная копия готова — файлов: {count}, размер: {size}.\n"
        ".env и виртуальные окружения не включены.",
    },
    "backup.too_large": {
        "en": "The archive is {size}, which exceeds Telegram's {limit} upload limit. Trim the "
        "hosted projects and try again.",
        "ru": "Архив весит {size} — это больше лимита Telegram в {limit}. Уменьшите объём "
        "данных проектов и попробуйте снова.",
    },
    "backup.failed": {"en": "Backup failed: {error}", "ru": "Не удалось создать резервную копию: {error}"},
    "alerts.title": {"en": "Alert rules", "ru": "Уведомления"},
    "alerts.page_hint": {
        "en": "Page {page}/{total}. Tap a rule to toggle delivery.",
        "ru": "Стр. {page}/{total}. Нажмите, чтобы включить или выключить.",
    },
    "alerts.on": {"en": "on", "ru": "вкл"},
    "alerts.off": {"en": "off", "ru": "выкл"},
    "alerts.throttle": {"en": " throttle {seconds}s", "ru": " интервал {seconds} с"},
    "alerts.enabled": {"en": "{kind} enabled.", "ru": "{kind}: включено."},
    "alerts.disabled": {"en": "{kind} disabled.", "ru": "{kind}: выключено."},
    "thresholds.title": {"en": "Alert thresholds", "ru": "Пороги уведомлений"},
    "thresholds.cpu": {"en": "CPU threshold", "ru": "Порог по ЦП"},
    "thresholds.memory": {"en": "Memory threshold", "ru": "Порог по памяти"},
    "thresholds.disk": {"en": "Disk threshold", "ru": "Порог по диску"},
    "thresholds.minimum_severity": {"en": "Minimum severity", "ru": "Минимальная важность"},
    "thresholds.quiet_hours": {"en": "Quiet hours", "ru": "Тихие часы"},
    "thresholds.quiet_hours_disabled": {"en": "disabled", "ru": "выключены"},
    "thresholds.quiet_hours_note": {
        "en": "Quiet hours suppress everything below critical.",
        "ru": "В тихие часы подавляются все уведомления, кроме критических.",
    },
    "thresholds.button_cpu": {"en": "CPU", "ru": "ЦП"},
    "thresholds.button_memory": {"en": "Memory", "ru": "Память"},
    "thresholds.button_disk": {"en": "Disk", "ru": "Диск"},
    "thresholds.button_cycle_severity": {
        "en": "Cycle minimum severity",
        "ru": "Сменить минимальную важность",
    },
    "thresholds.button_window": {"en": "Window", "ru": "Окно"},
    "thresholds.quiet_hours_on": {"en": "Quiet hours: on", "ru": "Тихие часы: вкл"},
    "thresholds.quiet_hours_off": {"en": "Quiet hours: off", "ru": "Тихие часы: выкл"},
    "thresholds.severity_now": {
        "en": "Minimum severity is now {severity}.",
        "ru": "Минимальная важность теперь: {severity}.",
    },
    "thresholds.quiet_enabled": {"en": "Quiet hours enabled.", "ru": "Тихие часы включены."},
    "thresholds.quiet_disabled": {"en": "Quiet hours disabled.", "ru": "Тихие часы выключены."},
    "thresholds.prompt_cpu": {
        "en": "Send the CPU alert threshold as a percentage between 1 and 100.",
        "ru": "Отправьте порог по ЦП в процентах от 1 до 100.",
    },
    "thresholds.prompt_memory": {
        "en": "Send the memory alert threshold as a percentage between 1 and 100.",
        "ru": "Отправьте порог по памяти в процентах от 1 до 100.",
    },
    "thresholds.prompt_disk": {
        "en": "Send the disk alert threshold as a percentage between 1 and 100.",
        "ru": "Отправьте порог по диску в процентах от 1 до 100.",
    },
    "thresholds.prompt_window": {
        "en": "Send the quiet-hours window as two UTC hours, for example 23 7.",
        "ru": "Отправьте окно тихих часов как два часа UTC через пробел, например 23 7.",
    },
    "thresholds.send_two_hours": {
        "en": "Send two UTC hours, for example 23 7.",
        "ru": "Отправьте два часа UTC, например 23 7.",
    },
    "thresholds.send_one_number": {"en": "Send a single whole number.", "ru": "Отправьте одно целое число."},
    "accounts.title": {"en": "GitHub accounts", "ru": "Аккаунты GitHub"},
    "accounts.none": {
        "en": "No accounts stored. Add one to clone private repositories.\n"
        "Public repositories work without an account.",
        "ru": "Аккаунты не добавлены. Добавьте, чтобы клонировать приватные репозитории.\n"
        "Публичные репозитории доступны без аккаунта.",
    },
    "accounts.added_on": {"en": "added {date}", "ru": "добавлен {date}"},
    "accounts.button_add": {"en": "Connect GitHub", "ru": "Подключить GitHub"},
    "accounts.button_delete": {"en": "Delete {label}", "ru": "Удалить {label}"},
    "accounts.deleted": {"en": "Account deleted.", "ru": "Аккаунт удалён."},
    "accounts.connect_intro": {
        "en": "Connecting a GitHub account lets you install and update private repositories.",
        "ru": "Подключение аккаунта GitHub позволяет устанавливать и обновлять приватные репозитории.",
    },
    "accounts.device_flow_title": {"en": "Connect GitHub", "ru": "Подключение GitHub"},
    "accounts.device_flow_body": {
        "en": "Open the link below, enter this code, and approve access:\n\n{code}\n\nWaiting for approval…",
        "ru": "Откройте ссылку ниже, введите этот код и подтвердите доступ:\n\n{code}\n\nЖду подтверждения…",
    },
    "accounts.device_flow_open": {
        "en": "Open github.com/login/device",
        "ru": "Открыть github.com/login/device",
    },
    "accounts.device_flow_success": {"en": "Connected as {username}.", "ru": "Подключено как {username}."},
    "accounts.device_flow_expired": {
        "en": "The code expired before it was approved. Try again.",
        "ru": "Код истёк до подтверждения. Попробуйте снова.",
    },
    "accounts.device_flow_denied": {"en": "Access was denied.", "ru": "В доступе отказано."},
    "accounts.fallback_title": {"en": "Add a GitHub account", "ru": "Добавление аккаунта GitHub"},
    "accounts.fallback_body": {
        "en": "Create a personal access token with the button below, then paste it here.\n\n"
        "Your message is deleted as soon as it is read and the token is encrypted at rest.",
        "ru": "Создайте персональный токен доступа по кнопке ниже, затем вставьте его сюда.\n\n"
        "Ваше сообщение удаляется сразу после прочтения, токен хранится в зашифрованном виде.",
    },
    "accounts.fallback_button": {"en": "Create a token", "ru": "Создать токен"},
    "accounts.invalid_token": {
        "en": "That token could not be verified with GitHub. Send a valid token or /cancel.",
        "ru": "Не удалось проверить токен через GitHub. Отправьте корректный токен или /cancel.",
    },
    "events.title": {"en": "Event history", "ru": "История событий"},
    "events.empty": {"en": "No events recorded yet.", "ru": "События ещё не зафиксированы."},
    "events.page_header": {"en": "Page {page}/{total}", "ru": "Стр. {page}/{total}"},
    "logs.title": {"en": "Recent output", "ru": "Недавний вывод"},
    "logs.empty": {"en": "No output captured yet.", "ru": "Вывод пока не зафиксирован."},
    "flow.nothing_to_cancel": {"en": "Nothing to cancel.", "ru": "Нечего отменять."},
    "flow.cancelled": {"en": "Cancelled.", "ru": "Отменено."},
    "help.title": {"en": "Fleet orchestrator", "ru": "Оркестратор ботов"},
    "help.body": {
        "en": "Every project lives in its own directory, runs inside its own sandbox, and can reach "
        "neither the orchestrator nor any other project.",
        "ru": "Каждый проект хранится в своей папке, работает в собственной песочнице и не имеет доступа "
        "ни к оркестратору, ни к другим проектам.",
    },
    "command.status": {"en": "Show the fleet dashboard", "ru": "Показать статус оркестратора"},
    "command.projects": {"en": "Manage installed projects", "ru": "Управление проектами"},
    "command.env": {
        "en": "Load environment variables into a project",
        "ru": "Загрузить переменные окружения в проект",
    },
    "command.logs": {"en": "Show recent output of a project", "ru": "Показать недавний вывод проекта"},
    "command.events": {"en": "Show the event history", "ru": "Показать историю событий"},
    "command.settings": {"en": "Configure alerts and accounts", "ru": "Настроить уведомления и аккаунты"},
    "command.start": {
        "en": "Open the main menu, or start a project by name",
        "ru": "Открыть главное меню или запустить проект по имени",
    },
    "command.stop": {
        "en": "Stop everything, or stop a project by name",
        "ru": "Остановить всё или остановить проект по имени",
    },
    "command.restart": {
        "en": "Restart everything, or restart a project by name",
        "ru": "Перезапустить всё или проект по имени",
    },
    "command.cancel": {"en": "Abort the current flow", "ru": "Отменить текущее действие"},
    "command.help": {"en": "Show the command list", "ru": "Показать список команд"},
}


def all_keys() -> frozenset[str]:
    return frozenset(STRINGS)
