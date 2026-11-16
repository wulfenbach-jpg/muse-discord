# BRIDGE.md: two agents, one channel, a thread per task

This fork of [muse-discord](https://github.com/cszach/muse-discord) adds
one thing: a **peer**, another agent the owner pairs this bot with. The
two work in a Discord channel the owner picks, open a thread per task,
give each other work and report back. Discord is the mailbox, and the
owner can read along or jump into any thread.

## What it changes (all of it)

| Piece | Where | What |
| --- | --- | --- |
| Inbound | `monitor.py` `trigger_verdict` | Every message the peer writes in its channels, or any thread under them, wakes the worker: no @mention needed, even under `who.bots: ignore`. The item carries `peer: {name, owners}`. |
| Own threads | `monitor.py` `trigger_verdict` | An owner's messages in a thread the bot opened wake it with no mention, like Hermes's threads (unless the message is addressed to someone else). Pinged in the peer's channel itself, the worker answers in a new thread on the owner's message. |
| Holds | `monitor.py` `peer_held`, `peer_holds.json` | The worker can stay asleep in a thread until the peer's message matches a regex, or until some hours pass. Held messages are recorded as handled (the sweep never requeues them), and the next wake sees them in its history. Only the peer is held, never the owner. |
| Outbound | `bin/discord-api.py peer-*` | `peer-thread` (new thread, first message), `peer-post`, `peer-read` and `peer-wait`, with no owner nonce, from the main chat or any run, only in the peer's channels and their threads. They @mention only the peer and un-archive threads when needed. |
| Relay | `bin/discord-api.py relay` / `relay-pending` / `relay-done`, `hooks/main-relay.sh` | The reply worker hands an owner's Discord request it can't do (cron, shell, files, memory) to the Muse's main chat, which does it with full tools and answers back in Discord. Only an owner's own message, checked by its nonce and re-read from Discord. |
| Orders | `worker-prompt.template.md`, PEER AGENT | Chain of command: owner -> this bot -> peer, and peer -> this bot. What the owner tells this bot to have the peer do counts as the owner's say-so. |
| Config | `peers:` in `config.yaml`, `muse_settings.parse_peers` | Validated by `bin/settings.py validate`. |
| Telemetry | `telemetry.py` | `TELEMETRY_URL = ""`: nothing is ever sent. |

Everything else stays upstream: loop limit (`who.bot_exchange_limit`),
bot-burst coalescing (one wake per 15 s burst), the injection filter,
proactive messages, @mentions from anyone in any thread, and the nonce
rules for every other subcommand.

## The loop

```bash
api=".venv/bin/python3 bin/discord-api.py"
$api peer-thread --until '^(DONE|BLOCKED)' "Flight prices" \
  "Find the 3 cheapest SFO-NRT fares in March. Reply DONE: <list> or BLOCKED: <why>."
# -> created thread 1571...; the peer's "on it" / progress lines wake nobody
# -> its "DONE: ..." wakes the worker, which answers or follows up:
$api peer-post --to 1571... --until '^DONE' "Now check refundable ones."
$api peer-read --to 1571... 30      # the whole story, if needed
$api peer-wait --to 1571... --off   # wake on everything again
```

Pinged by the owner in the channel itself, the worker opens a thread on
their message and answers there (`peer-thread --from <their message>
--solo "<title>" "<answer>"`). They keep talking in it without
mentions, and `peer-post --to <thread>` brings the peer in.

## From the main chat

The owner's Muse main chat (the native UI) is not the reply worker and
never reads its prompt. It uses the same commands from the package dir:
`peer-thread "<title>" "<task>"` to start a task with the peer (add
`--solo` for a thread with just the owner), `peer-post --to <thread>`
to continue, and `peer-read --to <thread>` to check on it. Anything
posted in a thread the bot opened, by the peer or the owner, then wakes
the reply worker, which carries the thread on. Put a line about this in
the Muse's own notes or memory so the main chat knows the commands
exist.

## The relay (Discord -> main chat)

The reply worker is a separate, deliberately limited session: it
doesn't use the shell, schedule jobs or write memory, and the main
chat never sees its conversations. When the owner asks for that kind
of thing in Discord, the worker relays it:

1. Worker: `discord-api.py --for <msg> --nonce <owner nonce> relay
   <channel> "<what + context>"`. The tool checks the nonce, re-reads
   the message from Discord, refuses anything not written by an owner,
   and records the owner's exact words in `main_requests.json`.
2. `hooks/main-relay.sh` (60 s) wakes the main chat with the request. A
   request still open after 30 minutes is handed out again.
3. Main chat: does it with full tools and memory, then `discord-api.py
   relay-done <id> "<answer>"`, which replies to the owner's message in
   Discord (`relay-done <id>` alone just closes it).

Register the hook in Muse like `update-watch.sh` (SETUP.md step 5):
60 s, delivered to the **main chat**, with this wake prompt:

> The owner asked you something from Discord; the payload has their
> exact words (`owner_words`: their instruction) and the Discord
> worker's context (`worker_note`). Do it here with your full tools and
> memory, saving to memory anything worth keeping from the context. Then
> run the payload's `done` command for each request with a short answer
> for Discord.

## Cost

The monitor is plain code, so nothing costs tokens while the peer is
quiet or held. A worker wakes only for a message that counts, once per
burst. Holds are the main saving: a long task costs one wake for its
result, not one per progress line. To limit runaway back-and-forth, set
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

Add to `config.yaml`: the peer's user id, and the channel whose threads
the two share (a thread id also works, for that thread alone):

```yaml
peers:
  - user_id: "<peer user id>"
    name: hermes
    channels: ["<channel id>"]
```

```bash
.venv/bin/python3 bin/settings.py validate
bash watchdog.sh            # restart the monitor: peers are read at start
.venv/bin/python3 bin/discord-api.py peer-thread "bridge test" "reply DONE when you see this"
```

The bot needs Create Public Threads and Send Messages in Threads in that
channel. The peer's side has to wake on this bot's messages: allowlist
this bot, and it must answer bots. Every `peer-*` message @mentions it.

## Updating

Don't take upstream releases directly (UPDATING.md checks out a tag,
which would drop this branch). Rebase `bridge` onto the new tag in the
fork, then `git pull` here. Conflicts can only be in the places listed
above, plus `hooks/mention-watch.sh` (`peer` in the wake payload).
