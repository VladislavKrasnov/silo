# Bot Fleet Orchestrator

![License](https://img.shields.io/badge/license-MIT-informational)
![Runs on](https://img.shields.io/badge/runs%20on-Linux%20%7C%20Docker-informational)
![Interface](https://img.shields.io/badge/interface-Telegram-informational)

**Run all your Telegram bots on one server, install and manage every one of them from a Telegram
chat, and never worry about one bot breaking another again.**

No terminal, no server dashboard, no juggling `.env` files by hand. You send a GitHub link or a
zip file to your bot, it does the rest — and every project it runs is locked in its own sealed
box, so a bug or a malicious dependency in one bot can never touch another bot, your server, or
your data.

## Get it running in five minutes

You need three things: a small server or computer with [Docker](https://docs.docker.com/get-docker/)
installed, a bot token from [@BotFather](https://t.me/BotFather), and your numeric Telegram ID
from [@userinfobot](https://t.me/userinfobot).

```
git clone https://github.com/VladislavKrasnov/silo.git
cd silo
cp .env.example .env
```

Open the new `.env` file and fill in two lines:

```
MASTER_BOT_TOKEN=the token BotFather gave you
ADMIN_IDS=your numeric Telegram ID
```

Then start it:

```
docker compose up -d --build
```

Open a chat with your bot and send `/start`. That's it — the control panel is live, and
**Projects → Install** is where you add your first bot.

## What it actually does

- **Installs bots for you.** Send a GitHub repository link or upload a zip file straight into the
  chat, and it's built, configured and running within moments — no manual setup, no SSH session.
- **Keeps every bot in its own sealed box.** Each project runs in an isolated environment that
  cannot see another bot's files, memory, or secrets — and cannot reach your server's files either.
  If one project misbehaves, everything else keeps running untouched.
- **Never stores your secrets in plain text.** API keys and tokens are encrypted the moment you
  send them, and are automatically hidden wherever they might otherwise leak — logs, error
  messages, alerts.
- **Watches your fleet around the clock.** You get an instant message the moment a bot crashes,
  fails to build, keeps restarting, runs low on required secrets, or the server itself is under
  pressure — so you find out before your users do.
- **Restarts itself when things go wrong.** Crashed bots come back automatically with sensible
  backoff, and everything can be configured to start on its own whenever the server reboots.
- **Speaks your language.** The whole control panel works in English and Russian, and switches
  automatically based on your Telegram settings.
- **Connects GitHub with one tap.** Link a GitHub account without ever copying a token by hand —
  approve a code on github.com and you're done.
- **Runs entirely on your own server.** Nothing is sent to a third party, there's no external
  service dependency beyond Telegram and GitHub, and everything — bots, secrets, settings — lives
  in one place you fully control.

## Commands

Everything is reachable through buttons, but the full command list also works if you'd rather
type:

| Command | What it does |
|---|---|
| `/start` | Opens the main menu, with a live status summary and quick-access buttons. |
| `/stop` | Lists running bots to pick one to stop (or stops it directly, with `/stop <name>`). |
| `/restart` | Lists running bots to pick one to restart (or restarts it directly, with `/restart <name>`). |
| `/status` | A detailed snapshot: server load, memory, disk, and per-bot health. |
| `/projects` | Install, inspect, rebuild, update, or remove any bot. |
| `/env` | Add, replace, or delete a bot's API keys and secrets. |
| `/logs <name>` | The most recent output from a bot. |
| `/events` | A history of everything that's happened across the fleet. |
| `/settings` | Alerts, thresholds, quiet hours, language, and connected GitHub accounts. |
| `/help` | The full command list. |
| `/cancel` | Backs out of any multi-step action. |

## Built on

Python, the Telegram Bot API, and industry-standard sandboxing (the same class of technology
container platforms use) and AES-256 encryption for anything sensitive. No paid add-ons, no
external database, no vendor lock-in — it's a single self-hosted application you own outright.

<details>
<summary><strong>Advanced: all configuration options</strong></summary>

Set these in your `.env` file. Only the first two are required — sensible defaults cover
everything else.

| Variable | Required | What it's for |
|---|---|---|
| `MASTER_BOT_TOKEN` | yes | Your Telegram bot's token. |
| `ADMIN_IDS` | yes | Telegram user IDs allowed to operate the panel, comma-separated. |
| `PROJECTS_ROOT_DIR` | no | Where installed bots live on disk. |
| `STATE_DIR` | no | Where the orchestrator keeps its own private data. |
| `ISOLATION_BACKEND` | no | Which sandbox technology to use: `auto`, `bubblewrap`, `docker`, or `native`. Leave on `auto`. |
| `CONTAINER_IMAGE` | no | The base image used when running bots through Docker isolation. |
| `AUTOSTART_PROJECTS` | no | Whether bots marked "autostart" come up automatically on boot. |
| `ORCHESTRATOR_MASTER_KEY` | no | An encryption key you supply yourself instead of letting one be generated. Set this if your server's disk isn't persistent. |
| `GITHUB_OAUTH_CLIENT_ID` | no | Enables one-tap GitHub linking instead of pasting a token by hand. |

</details>

<details>
<summary><strong>Advanced: running without Docker</strong></summary>

If you'd rather run it directly on a Linux server instead of through Docker:

```
apt-get install -y bubblewrap git python3-venv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in MASTER_BOT_TOKEN and ADMIN_IDS
python -m app
```

For a server that should keep it running permanently, wire it up as a `systemd` service pointing
at `python -m app`, with `Restart=on-failure`. Without `bubblewrap`, bots run without filesystem
isolation, which is fine for trying things out but not for anything you'd expose to real users.

</details>

## License

Released under the MIT License. See `LICENSE`.
