from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Union

PAISE_FACTOR = Decimal("100")
BASE_CONVERSION_FACTOR = Decimal("1000")  # 1000 g per kg, 1000 ml per L


def round_half_up(value: Decimal, places: int = 2) -> Decimal:
    """
    Rounds a Decimal value to `places` decimal places using standard ROUND_HALF_UP.
    Guarantees no float contamination or rounding bias.
    """
    if isinstance(value, float):
        raise TypeError("Floats are not permitted in monetary operations. Use Decimal or str.")

    if not isinstance(value, Decimal):
        raise TypeError(f"Expected Decimal, got {type(value).__name__}")

    exp = Decimal("10") ** -places
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def rupees_to_paise(amount: Union[Decimal, str, int]) -> int:
    """
    Converts rupees (as Decimal, str, or int) to an exact integer amount of paise.
    E.g.:
        Decimal("100.50") -> 10050
        "12.345" -> 1235 (rounded half up to 2 decimal places)
        "-10.00" -> -1000

    Raises TypeError if float is passed.
    Raises ValueError if invalid numeric string is provided.
    """
    if isinstance(amount, float):
        raise TypeError("Floats are strictly forbidden in monetary operations. Use Decimal or str.")

    if isinstance(amount, str):
        try:
            d_val = Decimal(amount.strip())
        except InvalidOperation as e:
            raise ValueError(f"Invalid monetary string: {amount!r}") from e
    elif isinstance(amount, (Decimal, int)):
        d_val = Decimal(amount)
    else:
        raise TypeError(f"Expected Decimal, int, or str, got {type(amount).__name__}")

    rounded = round_half_up(d_val, places=2)
    paise = (rounded * PAISE_FACTOR).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(paise)


def paise_to_rupees_str(paise: int) -> str:
    """
    Converts integer paise into a standard rupees string formatted to 2 decimal places.
    E.g.:
        10050 -> "100.50"
        5 -> "0.05"
        0 -> "0.00"
        -1234 -> "-12.34"
    """
    if not isinstance(paise, int):
        raise TypeError(f"Paise must be an integer, got {type(paise).__name__}")

    d_paise = Decimal(paise)
    rupees = d_paise / PAISE_FACTOR
    return f"{rupees:.2f}"


def calculate_line_total_paise(
    quantity_base: int,
    rate_paise_per_base: Union[Decimal, str],
) -> int:
    """
    Calculates line total in whole paise from an integer base quantity (grams, ml, pieces)
    and a precise rate in paise per base unit (Numeric(18,6)).
    Rounds to whole paise using ROUND_HALF_UP.

    E.g.:
      40,000 g flour @ 4.2 paise/g (from Rs 42/kg) -> 168,000 paise (Rs 1,680.00)
    """
    if not isinstance(quantity_base, int):
        raise TypeError(f"quantity_base must be an integer, got {type(quantity_base).__name__}")

    if isinstance(rate_paise_per_base, float):
        raise TypeError("Floats are strictly forbidden. Use Decimal or str.")

    if isinstance(rate_paise_per_base, str):
        d_rate = Decimal(rate_paise_per_base.strip())
    else:
        d_rate = rate_paise_per_base

    total_paise_dec = Decimal(quantity_base) * d_rate
    return int(total_paise_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def display_rate_to_base_paise_rate(
    rate_rupees_per_display_unit: Union[Decimal, str],
    display_unit: str,
) -> Decimal:
    """
    Converts a commercial display rate (e.g. Rs 42/kg or Rs 140/L or Rs 2.50/piece)
    into an exact rate in paise per base unit (paise/g, paise/ml, paise/piece)
    with up to 6 decimal places of precision.

    E.g.:
      Rs 42 / kg -> 4200 paise / 1000 g = Decimal("4.200000") paise/g
      Rs 140 / L -> 14000 paise / 1000 ml = Decimal("14.000000") paise/ml
      Rs 2.50 / piece -> 250 paise / 1 piece = Decimal("250.000000") paise/piece
    """
    if isinstance(rate_rupees_per_display_unit, float):
        raise TypeError("Floats are strictly forbidden. Use Decimal or str.")

    if isinstance(rate_rupees_per_display_unit, str):
        d_rupees = Decimal(rate_rupees_per_display_unit.strip())
    else:
        d_rupees = rate_rupees_per_display_unit

    total_paise = d_rupees * PAISE_FACTOR
    d_unit = display_unit.strip().lower()

    if d_unit in ("kg", "kilogram", "kilograms", "l", "litre", "liter", "litres", "liters"):
        rate_per_base = total_paise / BASE_CONVERSION_FACTOR
    else:
        rate_per_base = total_paise

    return rate_per_base.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
