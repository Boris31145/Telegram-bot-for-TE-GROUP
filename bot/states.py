"""FSM states for the order funnel."""

from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    # ── Step 0: choose service ─────────────────────────────────────────
    service = State()

    # ── Customs flow (5 data steps) ────────────────────────────────────
    # 1 — what goods?  2 — country of origin?
    # 3 — invoice value?  4 — urgency?  5 — phone
    customs_cargo     = State()
    customs_country   = State()
    invoice_value     = State()
    customs_urgency   = State()

    # ── Delivery flow (8 data steps) ───────────────────────────────────
    # 1 — country  2 — city  3 — cargo type  4 — weight
    # 5 — volume   6 — urgency  7 — incoterms  8 — phone
    country    = State()
    city       = State()
    cargo_type = State()
    weight     = State()
    volume     = State()
    urgency    = State()
    incoterms  = State()

    # ── Shared final steps ─────────────────────────────────────────────
    phone   = State()
    comment = State()
