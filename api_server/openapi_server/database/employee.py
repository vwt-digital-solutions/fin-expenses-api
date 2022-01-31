from dataclasses import dataclass
from google.cloud.datastore import Client
from datetime import datetime


@dataclass(frozen=True)
class Employee:
    upn: str
    name: str
    type: str
    email: str
    status: str
    company: str
    manager: str
    location: str
    initials: str
    last_name: str
    first_name: str
    department: str
    manager_id: int
    employee_id: int
    bank_account: str
    department_code: str
    date_in_service: datetime
    department_description: str

    reason_out_service: str = None
    date_out_service: datetime = None

    def to_dict(self) -> dict:
        return {
            "Achternaam": self.last_name,
            "Afdeling": self.department,
            "Afdeling Code": self.department_code,
            "Afdelingsomschrijving": self.department_description,
            "Bedrijf": self.company,
            "Datum_in_dienst": self.date_in_service,
            "Datum_uit_dienst": self.date_out_service,
            "IBAN": self.bank_account,
            "Initials": self.initials,
            "Locatie": self.location,
            "Manager": self.manager,
            "Manager_personeelsnummer": self.manager_id,
            "Personeelsnummer": self.employee_id,
            "Reden_einde_dienstverband": self.reason_out_service,
            "Status": self.status,
            "Type": self.type,
            "Voornaam": self.first_name,
            "email_address": self.email,
            "upn": self.upn
        }


class AFASEmployeeDatabase:
    def __init__(self):
        self.datastore = Client()

    def get_employee(self, employee_id: int) -> Employee:
        ...

    def query_employee_by_upn(self, upn: str) -> Employee:
        ...
