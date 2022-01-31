from dataclasses import dataclass, field
from datetime import datetime
from google.cloud.datastore import Client

from api_server.openapi_server.models.expense_data import ExpenseData
from api_server.openapi_server.models.status import Status


# From Google DataStore
@dataclass(frozen=True)
class Expense:
    amount: float
    auto_approved: bool
    claim_date: datetime
    cost_type: str
    employee: dict
    manager_type: str
    note: str
    status: dict
    transaction_date: datetime

    flags: dict = field(default_factory=dict)

    @property
    def status_text(self) -> str:
        return self.status.get("text", str())

    @classmethod
    def from_employee_model(cls, expense: ExpenseData) -> 'Expense':
        # HTML convert
        # Time convert
        ...

    @classmethod
    def update_by_model(cls, update: Status) -> 'Expense':
        ...

    def to_response_dict(self) -> dict:
        # Cost type parse
        ...


class ExpenseDatabase:
    def __init__(self):
        self.datastore = Client()

    def create_expense(self, expense: Expense) -> int:
        ...

    def get_expense(self, expense_id: int) -> Expense:
        ...

    def update_expense(self, expense_id: int, expense: Expense):
        ...

    def delete_expense(self, expense_id: int):
        ...

    def query_expenses_by_manager(self, manager_id: int) -> list[Expense]:
        ...

    def query_expenses_by_employee(self, employee_id: int) -> list[Expense]:
        ...

    def query_expenses_by_date(
            self,
            start: datetime = datetime.utcnow(),
            end: datetime = datetime.utcnow()
    ) -> list[Expense]:
        ...
