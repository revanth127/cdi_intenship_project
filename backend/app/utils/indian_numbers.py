from decimal import Decimal
from typing import Union


ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen"
]

TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"
]


def _two_digits_to_words(n: int) -> str:
    """Converts a number from 0 to 99 into words."""
    if n < 20:
        return ONES[n]
    tens_digit = n // 10
    ones_digit = n % 10
    if ones_digit == 0:
        return TENS[tens_digit]
    return f"{TENS[tens_digit]} {ONES[ones_digit]}"


def _three_digits_to_words(n: int) -> str:
    """Converts a number from 0 to 999 into words."""
    hundreds = n // 100
    rem = n % 100
    parts = []
    if hundreds > 0:
        parts.append(f"{ONES[hundreds]} Hundred")
    if rem > 0:
        parts.append(_two_digits_to_words(rem))
    return " ".join(parts)


def number_to_indian_words(num: int) -> str:
    """
    Converts a non-negative integer into words following the Indian numbering system:
    Crore (1,00,00,000), Lakh (1,00,000), Thousand (1,000), Hundred (100).
    """
    if num == 0:
        return "Zero"

    parts = []

    # Crores (10^7)
    crores = num // 10000000
    rem = num % 10000000
    if crores > 0:
        parts.append(f"{number_to_indian_words(crores)} Crore")

    # Lakhs (10^5)
    lakhs = rem // 100000
    rem = rem % 100000
    if lakhs > 0:
        parts.append(f"{_two_digits_to_words(lakhs)} Lakh")

    # Thousands (10^3)
    thousands = rem // 1000
    rem = rem % 1000
    if thousands > 0:
        parts.append(f"{_two_digits_to_words(thousands)} Thousand")

    # Hundreds and remainder
    if rem > 0:
        parts.append(_three_digits_to_words(rem))

    return " ".join(parts).strip()


def amount_in_words(amount_rupees: Union[int, float, Decimal], paise_input: bool = False) -> str:
    """
    Converts a rupee amount (or paise amount if paise_input=True) to words
    using standard Indian currency naming.
    Examples:
        7875 -> 'Rupees Seven Thousand Eight Hundred Seventy Five Only'
        100000 -> 'Rupees One Lakh Only'
        1234567.89 -> 'Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven and Eighty Nine Paise Only'
    """
    if paise_input:
        total_paise = int(amount_rupees)
        rupees = total_paise // 100
        paise = total_paise % 100
    else:
        dec_amt = Decimal(str(amount_rupees)).quantize(Decimal("0.01"))
        rupees = int(dec_amt)
        paise = int((dec_amt - Decimal(rupees)) * 100)

    if rupees == 0 and paise == 0:
        return "Rupees Zero Only"

    parts = []
    if rupees > 0:
        rupees_words = number_to_indian_words(rupees)
        parts.append(f"Rupees {rupees_words}")

    if paise > 0:
        paise_words = _two_digits_to_words(paise)
        if parts:
            parts.append(f"and {paise_words} Paise Only")
        else:
            parts.append(f"{paise_words} Paise Only")
    else:
        parts.append("Only")

    return " ".join(parts)
