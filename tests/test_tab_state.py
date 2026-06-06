import importlib.util
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "plugins" / "tab-title" / "tab-state.py"
)
SPEC = importlib.util.spec_from_file_location("tab_state", MODULE_PATH)
tab_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tab_state)


class TabStateTests(unittest.TestCase):
    def test_parse_linux_proc_stat_reads_ppid_and_tty_nr(self):
        stat = "1234 (claude code) S 4321 1234 1234 34816 0 0 0"

        self.assertEqual(tab_state.parse_linux_proc_stat(stat), (4321, 34816))

    def test_parse_linux_proc_stat_rejects_malformed_stat(self):
        self.assertIsNone(tab_state.parse_linux_proc_stat("1234 claude S 1"))

    def test_find_terminal_device_linux_walks_to_parent_tty(self):
        proc = {
            200: (100, 0),
            100: (1, 34816),
        }

        with (
            mock.patch.object(tab_state, "linux_proc_info", side_effect=proc.get),
            mock.patch.object(
                tab_state,
                "linux_tty_path",
                side_effect=lambda tty_nr: "/dev/pts/1" if tty_nr else "",
            ),
        ):
            self.assertEqual(tab_state.find_terminal_device_linux(200), "/dev/pts/1")


if __name__ == "__main__":
    unittest.main()
