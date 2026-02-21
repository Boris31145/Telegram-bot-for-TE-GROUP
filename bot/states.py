"""FSM states for the order funnel."""

from aiogram.fsm.state import State, StatesGroup


class OrderForm(StatesGroup):
    country = State()
    city = State()
    cargo_type = State()
    weight = State()
    volume = State()
    urgency = State()
    incoterms = State()
    phone = State()
    comment = State()
