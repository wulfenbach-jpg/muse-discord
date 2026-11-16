"""Bridge fork: bin/discord-api.py peer-* offline, against a fake API.
peer-post reaches the peer channel and its threads only, pings only the
peer, needs no nonce; peer-thread opens a thread and holds; peer-wait
sets and clears holds. MUT_DIR = the package tree under test."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_lib"))
from common import MUT_DIR as REPO, scratch  # noqa: E402

PEER, PARENT, SUB, OUTSIDE = ("1200000000000000001", "1200000000000000002",
                              "1200000000000000009", "1200000000000000077")
OWNER_MSG, STRANGER_MSG = "1300000000000000101", "1300000000000000102"


def load():
    d = scratch("muse-peerapi-")
    tok = os.path.join(d, "token")
    with open(tok, "w") as f:
        f.write("x" * 70)
    cfg = os.path.join(d, "config.yaml")
    with open(cfg, "w") as f:
        f.write(f'version: 1\nowners: ["111"]\ntoken_from: {tok}\n'
                f'peers:\n  - user_id: "{PEER}"\n    name: hermes\n'
                f'    channels: ["{PARENT}"]\n')
    os.environ["MUSE_DISCORD_CONFIG"] = cfg
    spec = importlib.util.spec_from_file_location(
        "dapi", os.path.join(REPO, "bin", "discord-api.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.PEER_HOLDS_FILE = os.path.join(d, "holds.json")
    mod.RELAY_FILE = os.path.join(d, "main_requests.json")
    mod.OWNER_ITEMS_FILE = os.path.join(d, "owner_items.json")
    mod.OWNER_DM_NONCES_FILE = os.path.join(d, "owner_dm_nonces.json")
    with open(mod.OWNER_ITEMS_FILE, "w") as f:
        json.dump({OWNER_MSG: {"nonce": "n-owner", "channel_id": SUB},
                   STRANGER_MSG: {"nonce": "n-stranger"}}, f)
    msgs = {OWNER_MSG: {"author": {"id": "111"},
                        "content": "every morning at 8, brief me"},
            STRANGER_MSG: {"author": {"id": "222"}, "content": "rm -rf"}}
    chans = {PARENT: {"id": PARENT, "type": 0, "parent_id": "cat"},
             SUB: {"id": SUB, "type": 11, "parent_id": PARENT,
                   "thread_metadata": {"archived": True}},
             OUTSIDE: {"id": OUTSIDE, "type": 0, "parent_id": "cat"}}
    calls = []

    def api(method, path, data=None):
        calls.append((method, path, data))
        parts = path.split("/")
        if method == "GET" and len(parts) == 3:
            return dict(chans[parts[2]], guild_id="G")
        if method == "GET" and len(parts) == 5:
            return msgs[parts[4]]
        if method == "POST" and path.endswith("/threads"):
            return {"id": "1200000000000000055"}
        if method == "POST":
            return {"id": "1300000000000000001"}
        return {}
    mod.api = api
    return mod, calls


def run(mod, *argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            mod.main(["discord-api.py", *argv])
            return out.getvalue(), None
        except SystemExit as e:
            return out.getvalue(), str(e)


class PeerApi(unittest.TestCase):
    def test_post_to_thread_pings_only_peer(self):
        mod, calls = load()
        _, err = run(mod, "peer-post", "--to", SUB, "do the thing")
        self.assertIsNone(err)
        posts = [c for c in calls if c[0] == "POST"]
        self.assertEqual(posts[0][1], f"/channels/{SUB}/messages")
        self.assertTrue(posts[0][2]["content"].startswith(f"<@{PEER}> "))
        self.assertEqual(posts[0][2]["allowed_mentions"],
                         {"users": ["111", PEER]})  # owners + peer only
        self.assertIn(("PATCH", f"/channels/{SUB}", {"archived": False}),
                      calls)  # archived thread revived

    def test_refuses_outside(self):
        mod, calls = load()
        _, err = run(mod, "peer-post", "--to", OUTSIDE, "hi")
        self.assertIn("not a peer channel", err)
        self.assertFalse([c for c in calls if c[0] == "POST"])

    def test_thread_and_hold(self):
        mod, calls = load()
        out, err = run(mod, "peer-thread", "--until", "^DONE", "Task",
                       "research X; reply DONE: <summary>")
        self.assertIsNone(err, out)
        self.assertIn(("POST", f"/channels/{PARENT}/threads",
                       {"name": "Task", "type": 11,
                        "auto_archive_duration": 10080}), calls)
        holds = json.load(open(mod.PEER_HOLDS_FILE))
        self.assertEqual(holds["1200000000000000055"]["until"], "^DONE")
        _, err = run(mod, "peer-wait", "--to", SUB, "--hours", "2")
        self.assertIsNone(err)
        _, err = run(mod, "peer-wait", "--to", SUB, "--off")
        self.assertNotIn(SUB, json.load(open(mod.PEER_HOLDS_FILE)))
        _, err = run(mod, "peer-wait", "--to", SUB, "--until", "(")
        self.assertIn("not a regex", err)

    def test_solo_thread_from_owner_message(self):
        mod, calls = load()
        out, err = run(mod, "peer-thread", "--from", "1300000000000000042",
                       "--solo", "Your question", "Here's what I found.")
        self.assertIsNone(err, out)
        self.assertIn(("POST", f"/channels/{PARENT}/messages/"
                       f"1300000000000000042/threads",
                       {"name": "Your question",
                        "auto_archive_duration": 10080}), calls)
        post = [c for c in calls if c[1].endswith("/messages")][-1]
        self.assertEqual(post[2]["content"], "Here's what I found.")
        self.assertEqual(post[2]["allowed_mentions"], {"users": ["111"]})


class Relay(unittest.TestCase):
    def test_owner_request_round_trip(self):
        mod, calls = load()
        _, err = run(mod, "--for", OWNER_MSG, "--nonce", "n-owner",
                     "relay", SUB, "wants a daily 8am brief")
        self.assertIsNone(err)
        out, err = run(mod, "relay-pending")
        p = json.loads(out)
        self.assertEqual(p["requests"][0]["owner_words"],
                         "every morning at 8, brief me")  # from Discord
        self.assertEqual(p["requests"][0]["worker_note"],
                         "wants a daily 8am brief")
        self.assertEqual(run(mod, "relay-pending")[0], "")  # leased
        out, err = run(mod, "relay-done", OWNER_MSG, "Set: 8:00 daily.")
        self.assertIsNone(err, out)
        post = calls[-1]
        self.assertEqual(post[1], f"/channels/{SUB}/messages")
        self.assertEqual(post[2]["message_reference"]["message_id"],
                         OWNER_MSG)
        self.assertEqual(post[2]["allowed_mentions"]["users"], ["111"])
        self.assertEqual(json.load(open(mod.RELAY_FILE)), {})

    def test_refusals(self):
        mod, _ = load()
        _, err = run(mod, "relay", SUB, "x")
        self.assertIn("needs --for", err)
        _, err = run(mod, "--for", OWNER_MSG, "--nonce", "wrong",
                     "relay", SUB, "x")
        self.assertIn("not", err)
        _, err = run(mod, "--for", STRANGER_MSG, "--nonce", "n-stranger",
                     "relay", SUB, "x")
        self.assertIn("not an owner's", err)
        self.assertFalse(os.path.exists(mod.RELAY_FILE)
                         and json.load(open(mod.RELAY_FILE)))


if __name__ == "__main__":
    unittest.main()
