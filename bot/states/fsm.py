from aiogram.fsm.state import State, StatesGroup


class CreatePost(StatesGroup):
    waiting_for_input = State()


class EditPost(StatesGroup):
    waiting_for_text = State()


class RewritePost(StatesGroup):
    waiting_for_prompt = State()


class EditPrompt(StatesGroup):
    collecting_parts = State()


class EditSchedule(StatesGroup):
    waiting_for_cron = State()


class EditProviders(StatesGroup):
    waiting_for_json = State()
