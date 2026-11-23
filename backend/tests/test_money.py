from decimal import Decimal
import pytest

from app.utils.money import paise_to_rupees_str, round_half_up, rupees_to_paise


class TestMoneyHelpers:
    """
    Unit tests for monetary helpers ensuring strict Decimal arithmetic,
    paise integer storage, and no float contamination.
    """

    def test_rupees_to_paise_exact(self):
        assert rupees_to_paise(Decimal("100.50")) == 10050
        assert rupees_to_paise("100.50") == 10050
        assert rupees_to_paise(Decimal("0.00")) == 0
        assert rupees_to_paise("0") == 0
        assert rupees_to_paise(Decimal("1.00")) == 100
        assert rupees_to_paise("0.01") == 1

    def test_rupees_to_paise_round_half_up(self):
        # Round half up checks
        assert rupees_to_paise("12.345") == 1235
        assert rupees_to_paise("12.344") == 1234
        assert rupees_to_paise(Decimal("12.345")) == 1235
        assert rupees_to_paise(Decimal("12.344")) == 1234
        assert rupees_to_paise("0.005") == 1
        assert rupees_to_paise("0.004") == 0

    def test_rupees_to_paise_negative_and_large(self):
        assert rupees_to_paise("-50.25") == -5025
        assert rupees_to_paise(Decimal("-10.00")) == -1000
        assert rupees_to_paise("10000000.99") == 1000000099

    def test_rupees_to_paise_whitespace_handling(self):
        assert rupees_to_paise("  450.75  ") == 45075

    def test_rupees_to_paise_rejects_float(self):
        with pytest.raises(TypeError, match="Floats are strictly forbidden"):
            rupees_to_paise(100.50)  # type: ignore

    def test_rupees_to_paise_invalid_input(self):
        with pytest.raises(ValueError, match="Invalid monetary string"):
            rupees_to_paise("abc")

        with pytest.raises(TypeError):
            rupees_to_paise(None)  # type: ignore

    def test_paise_to_rupees_str(self):
        assert paise_to_rupees_str(10050) == "100.50"
        assert paise_to_rupees_str(0) == "0.00"
        assert paise_to_rupees_str(5) == "0.05"
        assert paise_to_rupees_str(99) == "0.99"
        assert paise_to_rupees_str(123456) == "1234.56"
        assert paise_to_rupees_str(-5025) == "-50.25"
        assert paise_to_rupees_str(-5) == "-0.05"

    def test_paise_to_rupees_str_rejects_non_integer(self):
        with pytest.raises(TypeError, match="Paise must be an integer"):
            paise_to_rupees_str(100.5)  # type: ignore

        with pytest.raises(TypeError, match="Paise must be an integer"):
            paise_to_rupees_str("100")  # type: ignore

    def test_round_half_up(self):
        assert round_half_up(Decimal("2.675"), places=2) == Decimal("2.68")
        assert round_half_up(Decimal("2.674"), places=2) == Decimal("2.67")
        assert round_half_up(Decimal("2.5"), places=0) == Decimal("3")
        assert round_half_up(Decimal("1.5"), places=0) == Decimal("2")

    def test_round_half_up_rejects_float(self):
        with pytest.raises(TypeError, match="Floats are not permitted"):
            round_half_up(2.675)  # type: ignore
