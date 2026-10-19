"""Launcher integration tests for source, wheel and frozen executable semantics."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import teview_desktop

class DesktopLauncherTests(unittest.TestCase):
    def test_bundled_example_accessible(self):
        with tempfile.TemporaryDirectory() as temp:
            with teview_desktop.experiment_source('lamp', Path(temp)) as source:
                self.assertTrue(source.is_file())
                self.assertIn('base = "lamp"', source.read_text())

    def test_custom_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            first = teview_desktop.initialize_custom(workspace)
            first.write_text('my data', encoding='utf-8')
            self.assertEqual(teview_desktop.initialize_custom(workspace).read_text(), 'my data')

    def test_help_exit(self):
        with self.assertRaises(SystemExit) as result:
            teview_desktop.main(['--help'])
        self.assertEqual(result.exception.code, 0)

    def test_non_tty_menu_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as temp, patch('teview_desktop.sys.stdin.isatty', return_value=False):
            self.assertEqual(teview_desktop.main(['--workspace', temp]), 1)

if __name__ == '__main__':
    unittest.main()
