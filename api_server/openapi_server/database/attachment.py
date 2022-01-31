from dataclasses import dataclass
from google.cloud.storage import Client, Blob


@dataclass(frozen=True)
class AttachmentMeta:
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


class AttachmentDatabase:
    def __init__(self):
        self.storage = Client()

    def create_attachment(self, expense_id: int, attachment_name: str, content_type: str, content: bytes):
        ...

    def get_attachment(self, expense_id: int, attachment_name: str) -> AttachmentMeta:
        ...

    def delete_attachment(self, expense_id: int, attachment_name: str):
        ...

    def query_attachments_by_expense_id(self, expense_id: int) -> list[AttachmentMeta]:
        ...
