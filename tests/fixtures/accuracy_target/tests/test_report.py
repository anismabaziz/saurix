"""
The fixture's test suite. It exercises every call path it can and no others,
so the trace it produces is short enough to check by hand.
"""

import unittest

from calculator.report import indirect, label, total


class ReportTest(unittest.TestCase):
    """
    Exercises every call path the fixture has, and no others.
    """

    def test_total(self):
        """The two values are added."""
        self.assertEqual(total([1, 2]), 3)

    def test_label(self):
        """The total is rendered inside a label."""
        self.assertEqual(label([2, 3]), "total=5")

    def test_indirect(self):
        """A call reached through a variable still adds."""
        self.assertEqual(indirect([4, 5]), 9)
