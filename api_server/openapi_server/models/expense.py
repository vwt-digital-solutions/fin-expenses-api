from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# From API request
@dataclass(frozen=True)
class ExpenseStatus:
    status: str

    creditor_note: Optional[str] = None
    manager_note: Optional[str] = None
    amount: Optional[int] = None
    note: Optional[str] = None
    cost_type: Optional[str] = None
    transaction_date: Optional[datetime] = None
    rnote_id: Optional[int] = None
    rnote: Optional[str] = None


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

    flags: Optional[dict]

    @property
    def status_text(self) -> str:
        return self.status.get("text", str())
