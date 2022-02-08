from datetime import datetime
from dataclasses import dataclass
from google.cloud.storage import Client, Blob


@dataclass(frozen=True)
class FileMeta:
    bucket: str
    path: str
    content_type: str

    def download(self) -> bytes:
        ...

    @property
    def name(self) -> str:
        ...

    @classmethod
    def from_blob(cls, blob: Blob):
        ...


@dataclass(frozen=True)
class Export:
    export_date: datetime
    booking_file_blob: Blob
    payment_file_blob: Blob

    def to_response_dict(self):
        ...


class FileDatabase:
    def __init__(self):
        self.storage = Client()

    def create_attachment(self, expense_id: int, attachment_name: str, content_type: str, content: bytes):
        ...

    def get_attachment(self, expense_id: int, attachment_name: str) -> FileMeta:
        ...

    def delete_attachment(self, expense_id: int, attachment_name: str):
        ...

    def query_attachments_by_expense_id(self, expense_id: int) -> list[FileMeta]:
        ...

    def get_exports(self) -> list[Export]:
        ...

    def get_export(self, export_id: int) -> Export:
        ...
