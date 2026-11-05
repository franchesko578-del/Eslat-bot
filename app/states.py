"""Suhbat bosqichlari (FSM holatlari)."""
from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    phone = State()

class AddChannel(StatesGroup):
    chat_id = State()
    title = State()
    invite = State()

class CreateReminder(StatesGroup):
    text = State(); repeat = State(); date = State(); time = State(); custom = State()

class EditReminder(StatesGroup):
    text = State(); when = State()

class Broadcast(StatesGroup):
    text = State(); confirm = State()
