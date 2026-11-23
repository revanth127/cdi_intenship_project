from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Union


PAISE_FACTOR = Decimal("100")
ONE_CENT = Decimal("0.01")


def round_half_up(value: Decimal, places: int = 2) -> Decimal:
    """
    Rounds a Decimal value to `places` decimal places using standard ROUND_HALF_UP.
    Prevents float contamination and rounding bias.
    """
    if isinstance(value, float):
        raise TypeError("Floats are not permitted in monetary operations. Use Decimal or str.")

    if not isinstance(value, Decimal):
        raise TypeError(f"Expected Decimal, got {type(value).__name__}")

    exp = Decimal("10") ** -places
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def rupees_to_paise(amount: Union[Decimal, str]) -> int:
    """
    Converts rupees (as Decimal or string) to an exact integer amount of paise.
    E.g.:
        Decimal("100.50") -> 10050
        "12.345" -> 1235 (rounded half up to 2 places)
        "-10.00" -> -1000

    Raises TypeError if a float is passed.
    Raises ValueError / InvalidOperation if an invalid string is provided.
    """
    if isinstance(amount, float):
        raise TypeError("Floats are strictly forbidden in monetary operations. Use Decimal or str.")

    if isinstance(amount, str):
        try:
            d_val = Decimal(amount.strip())
        except InvalidOperation as e:
            raise ValueError(f"Invalid monetary string: {amount!r}") from e
    elif isinstance(amount, Decimal):
        d_val = amount
    else:
        raise TypeError(f"Expected Decimal or str, got {type(amount).__name__}")

    # Round to 2 decimal places using ROUND_HALF_UP
    rounded = round_half_up(d_val, places=2)
    # Convert to integer paise
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

    Raises TypeError if input is not an integer.
    """
    if not isinstance(paise, int):
        raise TypeError(f"Paise must be an integer, got {type(paise).__name__}")

    d_paise = Decimal(paise)
    rupees = d_paise / PAISE_FACTOR
    return f"{rupees:.2f}"
