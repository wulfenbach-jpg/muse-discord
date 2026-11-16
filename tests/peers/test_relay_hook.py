"""Bridge fork: hooks/main-relay.sh, offline, with the stand-in hook
runtime and a stub bin/discord-api.py: silent with nothing relayed or
nothing new, a wake with relay-pending's payload otherwise."""
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_lib"))
from common import MUT_DIR as REPO, scratch  # noqa: E402

RUNTIME = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "_lib", "hook_runtime.sh")


def run_hook(requests_text, stub_prints):
    d = scratch("muse-relayhook-")
    os.makedirs(os.path.join(d, "bin"))
    with open(os.path.join(d, "bin", "discord-api.py"), "w") as f:
        f.write(f"import sys\nassert sys.argv[1] == 'relay-pending'\n"
                f"print({stub_prints!r}, end='')\n")
    if requests_text is not None:
        with open(os.path.join(d, "main_requests.json"), "w") as f:
            f.write(requests_text)
    env = dict(os.environ, HATCH_HOOK_RUNTIME=RUNTIME, MUSE_DISCORD_DIR=d,
               HOOK_STATE=os.path.join(d, "state"))
    r = subprocess.run(["bash", os.path.join(REPO, "hooks", "main-relay.sh")],
                       env=env, capture_output=True, text=True, timeout=30)
    return r.stdout


class RelayHook(unittest.TestCase):
    def test_nothing_relayed(self):
        self.assertIn("SILENT: nothing relayed", run_hook(None, ""))

    def test_already_handed(self):
        self.assertIn("SILENT: relayed requests already handed out",
                      run_hook('{"1": {}}', ""))

    def test_wakes_main_chat(self):
        out = run_hook('{"1": {}}', '{"requests": [{"id": "1"}]}')
        self.assertIn("WAKE: muse-discord: the owner asked from Discord",
                      out)
        self.assertIn('{"requests": [{"id": "1"}]}', out)


if __name__ == "__main__":
    unittest.main()
