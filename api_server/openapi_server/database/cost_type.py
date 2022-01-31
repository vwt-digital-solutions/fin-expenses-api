from dataclasses import dataclass
from google.cloud.datastore import Client


@dataclass(frozen=True)
class CostType:
    active: bool
    auto_approve: bool
    description: dict
    grootboek: int
    manager_type: str
    message: dict
    min_amount: int
    omschrijving: str


class CostTypeDatabase:
    def __init__(self):
        self.datastore = Client()
        self._cached_cost_types: list[CostType] = []

    def get_cost_types(self) -> list[CostType]:
        ...

