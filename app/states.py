"""Suhbat bosqichlari (FSM holatlari)."""
from aiogram.fsm.state import State, StatesGroup


class CreateReminder(StatesGroup):
    text = State()
    repeat = State()
    date = State()
    time = State()
    custom = State()


class EditReminder(StatesGroup):
    text = State()
    when = State()


class Broadcast(StatesGroup):
    text = State()
    confirm = State()
