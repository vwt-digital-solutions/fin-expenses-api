from dataclasses import dataclass
from google.cloud.datastore import Client
from datetime import datetime
from expense import Expense


@dataclass(frozen=True)
class ExpenseJournalEntry:
    attributes_changed: list
    expense_id: int
    time: datetime
    user: str

    @classmethod
    def generate(cls, old: Expense, new: Expense):
        ...


class ExpenseJournalDatabase:
    def __init__(self):
        self.datastore = Client()

    def create_expense_journal_entry(self, entry: ExpenseJournalEntry):
        ...

    def get_expense_journal_entry(self, entry_id: int) -> ExpenseJournalEntry:
        ...

    def query_expense_journal_entry_by_time(self, start: datetime, end: datetime):
        ...
