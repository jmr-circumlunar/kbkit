import sqlite3
import unittest

from kbkit import __version__
from kbkit.cli import build_parser


class BootstrapTests(unittest.TestCase):
    def test_version_is_defined(self):
        self.assertEqual(__version__, "1.0.0")

    def test_cli_parser_accepts_doctor(self):
        args = build_parser().parse_args(["doctor"])
        self.assertEqual(args.command, "doctor")

    def test_sqlite_fts5_is_available(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
            connection.execute("INSERT INTO probe(content) VALUES (?)", ("kbkit",))
            rows = connection.execute("SELECT content FROM probe WHERE probe MATCH ?", ("kbkit",)).fetchall()
            self.assertEqual(rows, [("kbkit",)])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
