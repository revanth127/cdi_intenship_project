from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Union


class UnitOfMeasure(str, Enum):
    """
    Standard Units of Measure for food manufacturing raw materials,
    packaging items, and finished goods.
    """
    KILOGRAM = "KG"
    GRAM = "G"
    LITER = "L"
    MILLILITER = "ML"
    PIECE = "PCS"
    BOX = "BOX"
    PACKET = "PKT"


# Conversion factors to base units (KG for weight, L for volume)
_WEIGHT_FACTORS = {
    UnitOfMeasure.KILOGRAM: Decimal("1"),
    UnitOfMeasure.GRAM: Decimal("0.001"),
}

_VOLUME_FACTORS = {
    UnitOfMeasure.LITER: Decimal("1"),
    UnitOfMeasure.MILLILITER: Decimal("0.001"),
}


def convert_quantity(
    quantity: Union[Decimal, str],
    from_unit: UnitOfMeasure,
    to_unit: UnitOfMeasure,
    precision: int = 4,
) -> Decimal:
    """
    Converts BOM raw material quantities without using float.
    Only supports conversions between compatible units (weight to weight, volume to volume).
    """
    if isinstance(quantity, float):
        raise TypeError("Floats are not permitted in quantity operations. Use Decimal or str.")

    if isinstance(quantity, str):
        try:
            d_qty = Decimal(quantity.strip())
        except InvalidOperation as e:
            raise ValueError(f"Invalid quantity string: {quantity!r}") from e
    elif isinstance(quantity, Decimal):
        d_qty = quantity
    else:
        raise TypeError(f"Expected Decimal or str, got {type(quantity).__name__}")

    if from_unit == to_unit:
        return d_qty

    # Weight conversions
    if from_unit in _WEIGHT_FACTORS and to_unit in _WEIGHT_FACTORS:
        base_kg = d_qty * _WEIGHT_FACTORS[from_unit]
        target = base_kg / _WEIGHT_FACTORS[to_unit]
        exp = Decimal("10") ** -precision
        return target.quantize(exp, rounding=ROUND_HALF_UP)

    # Volume conversions
    if from_unit in _VOLUME_FACTORS and to_unit in _VOLUME_FACTORS:
        base_l = d_qty * _VOLUME_FACTORS[from_unit]
        target = base_l / _VOLUME_FACTORS[to_unit]
        exp = Decimal("10") ** -precision
        return target.quantize(exp, rounding=ROUND_HALF_UP)

    raise ValueError(f"Cannot convert incompatible units: {from_unit.value} to {to_unit.value}")
