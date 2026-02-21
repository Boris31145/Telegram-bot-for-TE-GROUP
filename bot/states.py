"""FSM states for the order funnel."""

from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    # ── Step 0: choose service ─────────────────────────────────────────
    service = State()

    # ── Customs flow (5 data steps) ────────────────────────────────────
    customs_direction = State()   # import / transit / export
    customs_country   = State()   # country of goods origin
    customs_cargo     = State()   # type of goods
    invoice_value     = State()   # declared customs value

    # ── Delivery flow (8 data steps) ───────────────────────────────────
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
