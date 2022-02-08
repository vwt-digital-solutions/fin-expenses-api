from dataclasses import dataclass
from typing import Optional

from google.cloud.datastore import Client
from datetime import datetime

from api_server.openapi_server.models.employee_profile import EmployeeProfile as UserProfileModel


@dataclass(frozen=True)
class UserProfile:
    locale: str
    last_updated: datetime = datetime.utcnow()

    def to_response_dict(self):
        return {
            "locale": self.locale or ""
        }

    @classmethod
    def from_employee_profile_model(cls, model: UserProfileModel):
        ...


class UserProfileDatabase:
    def __init__(self):
        self.datastore = Client()

    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        ...

    def update_user_profile(self, user_id: str, profile: UserProfile):
        ...
