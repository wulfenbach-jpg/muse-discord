"""Bridge fork: peers, offline. A peer's plain message in its own
channel triggers (even under who.bots: ignore); the same peer elsewhere,
or another bot in that channel, does not; a bad peers: entry fails
validation. MUT_DIR = the package tree under test."""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_lib"))
from common import MUT_DIR as REPO, scratch  # noqa: E402

PEER, THREAD, OTHER_CH = "1200000000000000001", "1200000000000000002", "101"
CFG = f"""version: 1
owners: ["111"]
token_from: /nonexistent
everywhere:
  who:
    bots: ignore
peers:
  - user_id: "{PEER}"
    name: hermes
    channels: ["{THREAD}"]
"""
PROBE = r"""
import importlib.util, io, json, os, sys, contextlib
sys.argv = ["x", "dummy-token"]
with contextlib.redirect_stdout(io.StringIO()):
    spec = importlib.util.spec_from_file_location("monitor", sys.argv_repo)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
m.BOT_ID = m.BOT_USER_ID = "999"
m.api_get = lambda path: (_ for _ in ()).throw(AssertionError(path))
m.owners_absent = lambda gid: False
st = {"last_seen": {}, "replied_to": [], "history": {},
      "rate": {"day": "", "day_count": 0, "users": {}},
      "guild_joined": {"G": 0}}
m.LEDGER_FILE = os.path.join(os.environ["TMPD"], "ledger.json")
m.PEER_HOLDS_FILE = os.path.join(os.environ["TMPD"], "holds.json")
SUB = "1200000000000000009"   # a thread under the peer's channel
m.CHANNELS[SUB] = {"name": "task", "guild_id": "G", "thread": True,
                   "parent_id": sys.argv_thread}
n = [0]
def msg(author, channel, bot=True, text="done: report attached"):
    n[0] += 1
    return {"id": str(1300000000000000000 + n[0]), "channel_id": channel,
            "guild_id": "G", "type": 0,
            "author": {"id": author, "username": "a", "bot": bot},
            "content": text,
            "timestamp": "2026-11-15T00:00:00+00:00", "mentions": []}
out = {}
with contextlib.redirect_stdout(io.StringIO()):
    for name, a, c in [("peer_in_thread", sys.argv_peer, sys.argv_thread),
                       ("peer_in_subthread", sys.argv_peer, SUB),
                       ("peer_elsewhere", sys.argv_peer, "101"),
                       ("other_bot_in_thread", "1200000000000000003",
                        sys.argv_thread)]:
        out[name] = m.classify_message(st, msg(a, c), "S #t", "G")
    import time
    with open(m.PEER_HOLDS_FILE, "w") as f:
        json.dump({SUB: {"until": "^(DONE|BLOCKED)",
                         "expires": time.time() + 60}}, f)
    out["held_ack"] = m.classify_message(
        st, msg(sys.argv_peer, SUB, text="on it, working"), "S #t", "G")
    out["owner_in_held"] = m.classify_message(
        st, dict(msg("111", SUB, bot=False, text="status?"),
                 mentions=[{"id": "999"}]), "S #t", "G")
    out["held_done"] = m.classify_message(
        st, msg(sys.argv_peer, SUB, text="DONE: shipped"), "S #t", "G")
    out["after_hold"] = m.classify_message(
        st, msg(sys.argv_peer, SUB, text="also, fyi"), "S #t", "G")
    out["ledger_has_hold"] = "peer hold" in open(m.LEDGER_FILE).read()
out["peers"] = [p["name"] for p in m.PEERS]
print(json.dumps(out))
"""


def run_probe(cfg):
    d = scratch("muse-peers-")
    path = os.path.join(d, "config.yaml")
    with open(path, "w") as f:
        f.write(cfg)
    env = dict(os.environ, MUSE_DISCORD_CONFIG=path, TMPD=d)
    code = (f"import sys; sys.argv_repo = {os.path.join(REPO, 'monitor.py')!r}"
            f"; sys.argv_peer = {PEER!r}; sys.argv_thread = {THREAD!r}\n"
            + PROBE)
    r = subprocess.run([sys.executable, "-c", code], env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def validate(cfg):
    d = scratch("muse-peers-v-")
    path = os.path.join(d, "config.yaml")
    with open(path, "w") as f:
        f.write(cfg)
    env = dict(os.environ, MUSE_DISCORD_CONFIG=path)
    return subprocess.run(
        [sys.executable, os.path.join(REPO, "bin", "settings.py"),
         "validate"], env=env, capture_output=True, text=True, timeout=60)


class Peers(unittest.TestCase):
    def test_trigger(self):
        r = run_probe(CFG)
        self.assertEqual(r["peers"], ["hermes"])
        self.assertEqual(r["peer_in_thread"], "mention")
        self.assertEqual(r["peer_in_subthread"], "mention")
        self.assertIsNone(r["peer_elsewhere"])
        self.assertIsNone(r["other_bot_in_thread"])

    def test_hold(self):
        r = run_probe(CFG)
        self.assertIsNone(r["held_ack"])           # held: no wake
        self.assertEqual(r["owner_in_held"], "mention")  # owner never held
        self.assertEqual(r["held_done"], "mention")  # condition met
        self.assertEqual(r["after_hold"], "mention")  # hold ended
        self.assertTrue(r["ledger_has_hold"])      # sweep won't requeue

    def test_validate(self):
        self.assertEqual(validate(CFG).returncode, 0, validate(CFG).stdout)
        bad = CFG.replace(f'channels: ["{THREAD}"]', 'channels: ["general"]')
        r = validate(bad)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("peers[0].channels", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
