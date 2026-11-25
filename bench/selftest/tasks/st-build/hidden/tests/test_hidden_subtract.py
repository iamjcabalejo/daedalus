import unittest

import calc


class SubtractTest(unittest.TestCase):
    def test_subtract(self):
        self.assertEqual(calc.subtract(5, 3), 2)

    def test_subtract_negative(self):
        self.assertEqual(calc.subtract(1, 4), -3)


if __name__ == "__main__":
    unittest.main()
