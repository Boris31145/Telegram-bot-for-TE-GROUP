"""FSM states for the order funnel."""

from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    service = State()

    # Customs flow
    customs_cargo = State()
    customs_country = State()
    invoice_value = State()
    customs_urgency = State()

    # Delivery flow
    country = State()
    city = State()
    cargo_type = State()
    weight = State()
    volume = State()
    urgency = State()
    incoterms = State()

    # Shared
    phone = State()
    comment = State()
