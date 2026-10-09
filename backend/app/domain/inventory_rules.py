from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def order_meters(unit_meters: float, quantity: float) -> float:
    if unit_meters <= 0 or quantity < 0:
        raise ValueError("规格米数必须大于 0，商品数量不能小于 0")
    amount = Decimal(str(unit_meters)) * Decimal(str(quantity))
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def stock_changes(old_flower: str | None, old_effect: float,
                  new_flower: str | None, new_effect: float) -> dict[str, float]:
    """Return signed stock deltas; sales are negative and refund restocks positive."""
    deltas: dict[str, float] = {}
    if old_flower and old_effect:
        deltas[old_flower] = deltas.get(old_flower, 0.0) + float(old_effect)
    if new_flower and new_effect:
        deltas[new_flower] = deltas.get(new_flower, 0.0) - float(new_effect)
    return {flower: round(delta, 2) for flower, delta in deltas.items() if abs(delta) >= 0.005}
