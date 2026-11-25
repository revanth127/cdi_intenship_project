from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Optional, Union


class UnitFamily(str, Enum):
    MASS = "MASS"
    VOLUME = "VOLUME"
    COUNT = "COUNT"


class Unit(str, Enum):
    # Mass (Base unit: Gram 'g')
    KG = "kg"
    G = "g"

    # Volume (Base unit: Millilitre 'ml')
    LITRE = "litre"
    L = "l"
    ML = "ml"

    # Countable (Base unit: Piece / Packet)
    PIECE = "piece"
    PACKET = "packet"
    CARTON = "carton"


# Mapping from recognized string representations to canonical unit enum and family
_UNIT_ALIASES: dict[str, Unit] = {
    "kg": Unit.KG,
    "kilogram": Unit.KG,
    "kilograms": Unit.KG,
    "g": Unit.G,
    "gram": Unit.G,
    "grams": Unit.G,
    "litre": Unit.LITRE,
    "liter": Unit.LITRE,
    "litres": Unit.LITRE,
    "liters": Unit.LITRE,
    "l": Unit.L,
    "ml": Unit.ML,
    "millilitre": Unit.ML,
    "milliliter": Unit.ML,
    "millilitres": Unit.ML,
    "milliliters": Unit.ML,
    "piece": Unit.PIECE,
    "pieces": Unit.PIECE,
    "pc": Unit.PIECE,
    "pcs": Unit.PIECE,
    "packet": Unit.PACKET,
    "packets": Unit.PACKET,
    "pkt": Unit.PACKET,
    "pkts": Unit.PACKET,
    "carton": Unit.CARTON,
    "cartons": Unit.CARTON,
    "box": Unit.CARTON,
    "boxes": Unit.CARTON,
}

_UNIT_FAMILY_MAP: dict[Unit, UnitFamily] = {
    Unit.KG: UnitFamily.MASS,
    Unit.G: UnitFamily.MASS,
    Unit.LITRE: UnitFamily.VOLUME,
    Unit.L: UnitFamily.VOLUME,
    Unit.ML: UnitFamily.VOLUME,
    Unit.PIECE: UnitFamily.COUNT,
    Unit.PACKET: UnitFamily.COUNT,
    Unit.CARTON: UnitFamily.COUNT,
}

# Conversion multipliers from unit to its family base unit:
# MASS -> Base unit is Gram (g)
# VOLUME -> Base unit is Millilitre (ml)
# COUNT -> Base unit is 1 piece / packet (Carton requires product-specific packets_per_carton)
_TO_BASE_FACTORS: dict[Unit, Decimal] = {
    Unit.KG: Decimal("1000"),
    Unit.G: Decimal("1"),
    Unit.LITRE: Decimal("1000"),
    Unit.L: Decimal("1000"),
    Unit.ML: Decimal("1"),
    Unit.PIECE: Decimal("1"),
    Unit.PACKET: Decimal("1"),
}

_FAMILY_BASE_UNITS: dict[UnitFamily, str] = {
    UnitFamily.MASS: "g",
    UnitFamily.VOLUME: "ml",
    UnitFamily.COUNT: "piece",
}


def parse_unit(unit_input: Union[Unit, str]) -> Unit:
    """Parses and normalizes a unit string or enum."""
    if isinstance(unit_input, Unit):
        return unit_input
    if isinstance(unit_input, str):
        normalized = unit_input.strip().lower()
        if normalized in _UNIT_ALIASES:
            return _UNIT_ALIASES[normalized]
    raise ValueError(f"Unknown or unsupported unit: {unit_input!r}")


def get_unit_family(unit_input: Union[Unit, str]) -> UnitFamily:
    """Returns the family (MASS, VOLUME, COUNT) for a given unit."""
    canonical_unit = parse_unit(unit_input)
    return _UNIT_FAMILY_MAP[canonical_unit]


def to_base(
    quantity: Union[Decimal, str, int],
    unit: Union[Unit, str],
    packets_per_carton: Optional[int] = None,
) -> int:
    """
    Converts a quantity in a given unit into an integer quantity in BASE UNITS:
      - Mass: grams (g). E.g. 40 kg -> 40000, 1.2 kg -> 1200
      - Volume: millilitres (ml). E.g. 10.5 L -> 10500
      - Count: pieces or packets. E.g. 200 packets -> 200
      - Carton: requires packets_per_carton (e.g. 10 cartons of 20 -> 200 packets)

    Strictly rejects float to prevent binary floating point contamination.
    """
    if isinstance(quantity, float):
        raise TypeError("Floats are strictly forbidden in unit operations. Use Decimal, int, or str.")

    if isinstance(quantity, str):
        try:
            d_qty = Decimal(quantity.strip())
        except InvalidOperation as exc:
            raise ValueError(f"Invalid quantity numeric string: {quantity!r}") from exc
    elif isinstance(quantity, (Decimal, int)):
        d_qty = Decimal(quantity)
    else:
        raise TypeError(f"Expected Decimal, int, or str, got {type(quantity).__name__}")

    canonical_unit = parse_unit(unit)

    if canonical_unit == Unit.CARTON:
        if packets_per_carton is None or packets_per_carton <= 0:
            raise ValueError(
                "Converting cartons to base units requires positive 'packets_per_carton' (carton size is product-specific)."
            )
        factor = Decimal(packets_per_carton)
    else:
        factor = _TO_BASE_FACTORS[canonical_unit]

    base_val = (d_qty * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(base_val)


def from_base(
    base_quantity: int,
    unit: Union[Unit, str],
    packets_per_carton: Optional[int] = None,
) -> Decimal:
    """
    Converts an integer quantity in BASE UNITS (grams, ml, or pieces) into the target unit:
      - Mass: 40000 g -> Decimal("40") kg
      - Volume: 10500 ml -> Decimal("10.5") L
      - Carton: 200 packets with 20 packets/carton -> Decimal("10") cartons
    """
    if not isinstance(base_quantity, int):
        raise TypeError(f"Base quantity must be an integer, got {type(base_quantity).__name__}")

    canonical_unit = parse_unit(unit)

    if canonical_unit == Unit.CARTON:
        if packets_per_carton is None or packets_per_carton <= 0:
            raise ValueError(
                "Converting base units to cartons requires positive 'packets_per_carton'."
            )
        factor = Decimal(packets_per_carton)
    else:
        factor = _TO_BASE_FACTORS[canonical_unit]

    result = Decimal(base_quantity) / factor
    # Normalize trailing zeros if whole
    return result.normalize() if result == result.to_integral() else result


def convert_units(
    quantity: Union[Decimal, str, int],
    from_unit: Union[Unit, str],
    to_unit: Union[Unit, str],
    packets_per_carton: Optional[int] = None,
) -> Decimal:
    """
    Converts between two units within the same family.
    Raises ValueError when attempting to convert across families (e.g. mass to volume).
    """
    canonical_from = parse_unit(from_unit)
    canonical_to = parse_unit(to_unit)

    family_from = _UNIT_FAMILY_MAP[canonical_from]
    family_to = _UNIT_FAMILY_MAP[canonical_to]

    if family_from != family_to:
        raise ValueError(
            f"Cannot convert across unit families: {family_from.value} ({canonical_from.value}) to {family_to.value} ({canonical_to.value})"
        )

    base_qty = to_base(quantity, canonical_from, packets_per_carton=packets_per_carton)
    return from_base(base_qty, canonical_to, packets_per_carton=packets_per_carton)


def cartons_to_packets(cartons: Union[int, Decimal], packets_per_carton: int) -> int:
    """
    Product-specific packaging helper converting cartons to total packet count.
    E.g. 10 cartons of 20 packets = 200 packets.
    """
    if isinstance(cartons, float):
        raise TypeError("Floats are strictly forbidden. Use int or Decimal.")
    if packets_per_carton <= 0:
        raise ValueError("packets_per_carton must be greater than zero.")
    return int((Decimal(cartons) * Decimal(packets_per_carton)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
