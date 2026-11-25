import unittest

import calc


class CalcTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(2, 3), 5)

    def test_divide(self):
        self.assertEqual(calc.divide(6, 3), 2)


if __name__ == "__main__":
    unittest.main()
