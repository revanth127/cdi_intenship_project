from decimal import Decimal
import os
import sys
import unittest

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.money import (
    calculate_line_total_paise,
    display_rate_to_base_paise_rate,
    paise_to_rupees_str,
    round_half_up,
    rupees_to_paise,
)


class TestMoneyHelpers(unittest.TestCase):
    """
    Unit tests for monetary helpers ensuring strict Decimal arithmetic,
    paise integer storage, 6-decimal-place base unit rates, and no float contamination.
    """

    def test_rupees_to_paise_exact(self):
        self.assertEqual(rupees_to_paise(Decimal("100.50")), 10050)
        self.assertEqual(rupees_to_paise("100.50"), 10050)
        self.assertEqual(rupees_to_paise(Decimal("0.00")), 0)
        self.assertEqual(rupees_to_paise("0"), 0)
        self.assertEqual(rupees_to_paise(Decimal("1.00")), 100)
        self.assertEqual(rupees_to_paise("0.01"), 1)

    def test_rupees_to_paise_round_half_up(self):
        self.assertEqual(rupees_to_paise("12.345"), 1235)
        self.assertEqual(rupees_to_paise("12.344"), 1234)
        self.assertEqual(rupees_to_paise(Decimal("12.345")), 1235)
        self.assertEqual(rupees_to_paise(Decimal("12.344")), 1234)
        self.assertEqual(rupees_to_paise("0.005"), 1)
        self.assertEqual(rupees_to_paise("0.004"), 0)

    def test_rupees_to_paise_negative_and_large(self):
        self.assertEqual(rupees_to_paise("-50.25"), -5025)
        self.assertEqual(rupees_to_paise(Decimal("-10.00")), -1000)
        self.assertEqual(rupees_to_paise("10000000.99"), 1000000099)

    def test_rupees_to_paise_rejects_float(self):
        with self.assertRaises(TypeError):
            rupees_to_paise(100.50)  # type: ignore

    def test_paise_to_rupees_str(self):
        self.assertEqual(paise_to_rupees_str(10050), "100.50")
        self.assertEqual(paise_to_rupees_str(0), "0.00")
        self.assertEqual(paise_to_rupees_str(5), "0.05")
        self.assertEqual(paise_to_rupees_str(99), "0.99")
        self.assertEqual(paise_to_rupees_str(123456), "1234.56")
        self.assertEqual(paise_to_rupees_str(-5025), "-50.25")

    def test_paise_to_rupees_str_rejects_non_integer(self):
        with self.assertRaises(TypeError):
            paise_to_rupees_str(100.5)  # type: ignore

    def test_round_half_up(self):
        self.assertEqual(round_half_up(Decimal("2.675"), places=2), Decimal("2.68"))
        self.assertEqual(round_half_up(Decimal("2.674"), places=2), Decimal("2.67"))
        self.assertEqual(round_half_up(Decimal("2.5"), places=0), Decimal("3"))
        self.assertEqual(round_half_up(Decimal("1.5"), places=0), Decimal("2"))

    def test_display_rate_to_base_paise_rate(self):
        # Rs 42/kg = 4200 paise / 1000 g = 4.2 paise/g
        rate_flour = display_rate_to_base_paise_rate("42", "kg")
        self.assertEqual(rate_flour, Decimal("4.200000"))

        # Rs 140/L = 14000 paise / 1000 ml = 14.0 paise/ml
        rate_oil = display_rate_to_base_paise_rate("140", "L")
        self.assertEqual(rate_oil, Decimal("14.000000"))

        # Rs 200/kg = 20000 paise / 1000 g = 20.0 paise/g
        rate_spice = display_rate_to_base_paise_rate("200", "kg")
        self.assertEqual(rate_spice, Decimal("20.000000"))

        # Rs 2.50/piece = 250 paise / 1 piece = 250.0 paise/piece
        rate_pouch = display_rate_to_base_paise_rate("2.50", "piece")
        self.assertEqual(rate_pouch, Decimal("250.000000"))

    def test_calculate_line_total_paise(self):
        # 40,000 g flour @ 4.2 paise/g -> 168,000 paise (= Rs 1,680.00)
        self.assertEqual(calculate_line_total_paise(40000, Decimal("4.200000")), 168000)

        # 10,000 ml oil @ 14.0 paise/ml -> 140,000 paise (= Rs 1,400.00)
        self.assertEqual(calculate_line_total_paise(10000, Decimal("14.000000")), 140000)

        # 1,200 g spice @ 20.0 paise/g -> 24,000 paise (= Rs 240.00)
        self.assertEqual(calculate_line_total_paise(1200, Decimal("20.000000")), 24000)

        # 200 pouches @ 250.0 paise/piece -> 50,000 paise (= Rs 500.00)
        self.assertEqual(calculate_line_total_paise(200, Decimal("250.000000")), 50000)

        # Fractional paise rounding with ROUND_HALF_UP:
        # 3 g @ 4.255 paise/g = 12.765 paise -> 13 paise
        self.assertEqual(calculate_line_total_paise(3, Decimal("4.255000")), 13)


if __name__ == "__main__":
    unittest.main()
