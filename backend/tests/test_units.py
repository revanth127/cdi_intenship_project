from decimal import Decimal
import os
import sys
import unittest

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.units import (
    Unit,
    UnitFamily,
    cartons_to_packets,
    convert_units,
    from_base,
    get_unit_family,
    parse_unit,
    to_base,
)


class TestUnitConversions(unittest.TestCase):
    """
    Unit conversion tests covering:
    - 40 kg -> 40000 g
    - 10.5 L -> 10500 ml
    - 1.2 kg -> 1200 g
    - 10 cartons of 20 packets -> 200 packets
    - Conversion across unit families raises ValueError
    - from_base reversibility
    - Float rejection
    """

    def test_required_conversions_to_base(self):
        # 40 kg -> 40000
        self.assertEqual(to_base(Decimal("40"), "kg"), 40000)
        self.assertEqual(to_base("40", "kg"), 40000)

        # 10.5 L -> 10500 ml
        self.assertEqual(to_base(Decimal("10.5"), "L"), 10500)
        self.assertEqual(to_base(Decimal("10.5"), "litre"), 10500)
        self.assertEqual(to_base("10.5", "l"), 10500)

        # 1.2 kg -> 1200 g
        self.assertEqual(to_base(Decimal("1.2"), "kg"), 1200)
        self.assertEqual(to_base("1.2", "kg"), 1200)

        # 10 cartons of 20 packets -> 200 packets
        self.assertEqual(to_base(Decimal("10"), "carton", packets_per_carton=20), 200)
        self.assertEqual(cartons_to_packets(10, 20), 200)

    def test_from_base_conversions(self):
        # 40000 g -> 40 kg
        self.assertEqual(from_base(40000, "kg"), Decimal("40"))

        # 10500 ml -> 10.5 L
        self.assertEqual(from_base(10500, "L"), Decimal("10.5"))

        # 1200 g -> 1.2 kg
        self.assertEqual(from_base(1200, "kg"), Decimal("1.2"))

        # 200 packets -> 10 cartons (when 20 pkts/carton)
        self.assertEqual(from_base(200, "carton", packets_per_carton=20), Decimal("10"))

    def test_convert_within_same_family(self):
        # Mass: kg to g and g to kg
        self.assertEqual(convert_units(Decimal("2.5"), "kg", "g"), Decimal("2500"))
        self.assertEqual(convert_units(Decimal("500"), "g", "kg"), Decimal("0.5"))

        # Volume: L to ml and ml to L
        self.assertEqual(convert_units(Decimal("3"), "L", "ml"), Decimal("3000"))
        self.assertEqual(convert_units(Decimal("750"), "ml", "L"), Decimal("0.75"))

    def test_cross_family_conversions_raise_error(self):
        # Mass to Volume
        with self.assertRaises(ValueError):
            convert_units(Decimal("10"), "kg", "L")

        # Volume to Mass
        with self.assertRaises(ValueError):
            convert_units(Decimal("500"), "ml", "g")

        # Mass to Count
        with self.assertRaises(ValueError):
            convert_units(Decimal("2"), "kg", "piece")

        # Count to Volume
        with self.assertRaises(ValueError):
            convert_units(Decimal("50"), "piece", "ml")

    def test_carton_without_packets_per_carton_raises(self):
        with self.assertRaises(ValueError):
            to_base(Decimal("5"), "carton")

        with self.assertRaises(ValueError):
            from_base(100, "carton")

    def test_reject_float(self):
        with self.assertRaises(TypeError):
            to_base(40.0, "kg")  # type: ignore

        with self.assertRaises(TypeError):
            convert_units(1.2, "kg", "g")  # type: ignore

        with self.assertRaises(TypeError):
            cartons_to_packets(10.0, 20)  # type: ignore

    def test_unknown_unit_raises(self):
        with self.assertRaises(ValueError):
            parse_unit("lightyear")


if __name__ == "__main__":
    unittest.main()
