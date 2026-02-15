import unittest

from yaml_cli_ui.engine import PipelineEngine


class EngineTests(unittest.TestCase):
    def test_short_map_and_string_arg(self):
        engine = PipelineEngine({"version": 1, "actions": {}})
        scope = {
            "vars": {},
            "form": {"url": "http://x", "cookies": ["a", "b"], "enabled": True},
            "env": {},
            "cwd": ".",
            "home": ".",
            "temp": ".",
            "os": "nt",
            "step": {},
            "len": len,
            "empty": lambda x: x in (None, "", []),
            "exists": lambda _: True,
        }
        argv = engine.build_argv([
            {"--cookies": "${form.cookies}"},
            "${form.url}",
        ], scope)
        self.assertEqual(argv, ["--cookies", "a", "--cookies", "b", "http://x"])

    def test_extended_arg_tri_bool_false_opt(self):
        engine = PipelineEngine({"version": 1, "actions": {}})
        scope = {
            "vars": {},
            "form": {"subs": "false"},
            "env": {},
            "cwd": ".",
            "home": ".",
            "temp": ".",
            "os": "nt",
            "step": {},
            "len": len,
            "empty": lambda x: x in (None, "", []),
            "exists": lambda _: True,
        }
        argv = engine.build_argv([
            {
                "opt": "--write-subs",
                "from": "${form.subs}",
                "false_opt": "--no-write-subs",
                "mode": "flag",
            }
        ], scope)
        self.assertEqual(argv, ["--no-write-subs"])


if __name__ == "__main__":
    unittest.main()
