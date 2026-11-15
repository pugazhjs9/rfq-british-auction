"""Who may see which supplier.

A British auction is open about prices but not about who is bidding. Buyers
see every supplier. A supplier sees its own bids by name and each competitor
under an alias ("Supplier B"). Aliases are handed out in the order suppliers
first bid on the RFQ, so one never changes once given. They are assigned per
RFQ, so a competitor can't be followed from one auction to the next.

This is enforced on the server: a name the viewer may not see is never sent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from app.models import User, UserRole


def alias(index: int) -> str:
    """0 -> 'Supplier A', 25 -> 'Supplier Z', 26 -> 'Supplier AA', like spreadsheet columns."""
    letters = ""
    n = index + 1
    while n:
        n, remainder = divmod(n - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return f"Supplier {letters}"


def assign_aliases(supplier_ids_in_bid_order: Iterable[int]) -> dict[int, str]:
    """Give each supplier the next alias the first time it appears."""
    aliases: dict[int, str] = {}
    for supplier_id in supplier_ids_in_bid_order:
        if supplier_id not in aliases:
            aliases[supplier_id] = alias(len(aliases))
    return aliases


@dataclass(frozen=True)
class View:
    """How one viewer sees the suppliers on one RFQ. The default sees everyone."""

    viewer_id: int | None = None
    sees_everyone: bool = True
    companies: Mapping[int, str] = field(default_factory=dict)  # supplier id -> company
    aliases: Mapping[int, str] = field(default_factory=dict)  # supplier id -> alias

    @classmethod
    def of(cls, viewer: User | None, **names: Mapping[int, str]) -> View:
        """Buyers see everyone. A supplier sees only itself, and an anonymous viewer no one."""
        sees_everyone = viewer is not None and viewer.role is UserRole.BUYER
        return cls(viewer.id if viewer else None, sees_everyone, **names)

    def sees(self, supplier_id: int) -> bool:
        return self.sees_everyone or supplier_id == self.viewer_id

    def name(self, supplier_id: int) -> str:
        return self.companies[supplier_id] if self.sees(supplier_id) else self.aliases[supplier_id]
