"""First-install guidance belongs to the data directory, not a browser origin."""
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from zhishi.domain import models, settingsvc

STATE_KEY = 'ui.onboarding.v1'
Status = Literal['pending', 'completed', 'skipped', 'existing']


class OnboardingState(BaseModel):
    status: Status
    has_history: bool
    show_automatically: bool


class OnboardingFinish(BaseModel):
    outcome: Literal['completed', 'skipped']


def has_history(db: Session) -> bool:
    # Include soft-deleted records and saved configurations. Built-in skills,
    # default settings and an empty workspace are startup scaffolding.
    domains = (models.Task, models.Event, models.Goal, models.Habit,
               models.JournalEntry, models.TimeLog, models.LibraryFile,
               models.InboxItem, models.ResearchProject, models.LedgerEntry,
               models.Bill, models.AIMessage, models.AIConfig, models.MCPServer)
    return any(db.scalar(select(model.id).limit(1)) is not None for model in domains)


def initialize(db: Session, *, new_database: bool) -> None:
    if not settingsvc.get_setting(db, STATE_KEY):
        state = 'pending' if new_database and not has_history(db) else 'existing'
        settingsvc.set_setting(db, STATE_KEY, state)
    elif settingsvc.get_setting(db, STATE_KEY) == 'pending' and has_history(db):
        settingsvc.set_setting(db, STATE_KEY, 'existing')


def read(db: Session) -> OnboardingState:
    value = settingsvc.get_setting(db, STATE_KEY, 'existing')
    status: Status = value if value in ('pending', 'completed', 'skipped', 'existing') else 'existing'
    history = has_history(db)
    return OnboardingState(status=status, has_history=history,
                           show_automatically=status == 'pending' and not history)


def finish(db: Session, outcome: Literal['completed', 'skipped']) -> OnboardingState:
    if settingsvc.get_setting(db, STATE_KEY) != 'completed':
        settingsvc.set_setting(db, STATE_KEY, outcome)
    return read(db)
