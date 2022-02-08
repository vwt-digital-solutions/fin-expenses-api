from dataclasses import dataclass
from typing import Optional

from google.cloud.datastore import Client
from datetime import datetime

from api_server.openapi_server.models.push_token import PushToken as PushTokenModel


@dataclass(frozen=True)
class PushToken:
    app_version: str
    bundle_id: str
    device_id: str
    os_platform: str
    os_version: str
    push_token: str
    unique_name: str

    last_updated: datetime = datetime.utcnow()

    def to_response_dict(self):
        return {

        }

    @classmethod
    def from_push_token_model(cls, model: PushTokenModel):
        ...


class PushTokenDatabase:
    def __init__(self):
        self.datastore = Client()

    def get_push_token(self, key: str) -> Optional[PushToken]:
        ...

    def update_push_token_by_user_id(self, user_id: str, push_token: PushToken):
        ...
