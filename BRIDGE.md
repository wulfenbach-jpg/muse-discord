# BRIDGE.md: two agents, one thread

This fork of [muse-discord](https://github.com/cszach/muse-discord) adds
one thing: a **peer**, another agent the owner pairs this bot with. The
two talk in a Discord channel or thread the owner picks, give each
other work and report back. Discord is the mailbox, and the owner can
read along.

## What it changes (all of it)

| Piece | Where | What |
| --- | --- | --- |
| Inbound | `monitor.py` `trigger_verdict` | Every message the peer writes in its channels wakes the worker: no @mention needed, even under `who.bots: ignore`. The item carries `peer: {name, owners}`. |
| Outbound | `bin/discord-api.py peer-post` / `peer-read` | Post to and read the peer's channel with no owner nonce, from the main chat or any run. They @mention only the peer and un-archive the thread when needed. |
| Orders | `worker-prompt.template.md`, PEER AGENT | Chain of command: owner -> this bot -> peer, and peer -> this bot. What the owner tells this bot to have the peer do counts as the owner's say-so. |
| Config | `peers:` in `config.yaml`, `muse_settings.parse_peers` | Validated by `bin/settings.py validate`. |
| Telemetry | `telemetry.py` | `TELEMETRY_URL = ""`: nothing is ever sent. |

Everything else stays upstream: loop limit (`who.bot_exchange_limit`),
bot-burst coalescing (one wake per 15 s burst), the injection filter,
proactive messages, the nonce rules for every other subcommand.

## Cost

The monitor is plain code, so nothing costs tokens while the thread is
quiet. A worker wakes only when the peer actually writes, once per
burst. Pleasantries are what cost money, and the prompt tells the worker
to answer acks with `silent`. To limit runaway back-and-forth, set
`who.bot_exchange_limit` (1-50) for the server. The count resets when a
human writes in the thread.

## Set up (on the bot's machine)

```bash
cd ~/workspace/muse-discord
git remote rename origin upstream
git remote add origin https://github.com/<you>/muse-discord.git
git stash -u            # local edits (e.g. a blanked telemetry URL): the branch has them
git fetch origin && git checkout -B bridge origin/bridge
python3 bin/render-worker-prompt.py --media <same as before>   # adds PEER AGENT
```

Add to `config.yaml` (ids are the peer's user id and the shared thread):

```yaml
peers:
  - user_id: "<peer user id>"
    name: hermes
    channels: ["<thread id>"]
```

```bash
.venv/bin/python3 bin/settings.py validate
bash watchdog.sh            # restart the monitor: peers are read at start
.venv/bin/python3 bin/discord-api.py peer-post "ping from the bridge"
.venv/bin/python3 bin/discord-api.py peer-read 5
```

The peer's side has to wake on this bot's messages: allowlist this bot,
and it must answer bots. `peer-post` @mentions the peer every time.

## Updating

Don't take upstream releases directly (UPDATING.md checks out a tag,
which would drop this branch). Rebase `bridge` onto the new tag in the
fork, then `git pull` here. Conflicts can only be in the five places
listed above.
