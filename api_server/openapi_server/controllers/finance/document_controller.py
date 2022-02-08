from connexion import request
from datetime import datetime, timedelta
from flask import jsonify, make_response, Response
from google.cloud.storage import Blob

from api_server.openapi_server.controllers.translate_responses import make_response_translated
from api_server.openapi_server.database.document import FileDatabase, Export
from api_server.openapi_server.database.expense import ExpenseDatabase, Expense

DOCUMENT_DB = FileDatabase()
EXPENSE_DB = ExpenseDatabase()


def create_export():
    expenses: list[Expense] = EXPENSE_DB.query_expenses_by_status("approved")  # TODO: Not hardcode.
    export: Export = None  # TODO: Make export from expenses

    result = jsonify({
        "file_list": [
            export.to_response_dict()
        ]
    })

    return make_response(result, 200)


def get_export_by_type(document_id: int, document_type: str):
    export: Export = DOCUMENT_DB.get_export(document_id)

    if not export:
        return make_response_translated("Document niet gevonden", 404)
    elif document_type == "payment_file":
        blob = export.payment_file_blob
    elif document_type == "booking_file":
        blob = export.booking_file_blob
    else:
        return make_response_translated("Document niet gevonden", 404)

    mime_type = blob.content_type

    return Response(
        blob.download_as_bytes(),
        headers={
            "Content-Type": mime_type,
            "charset": "utf-8",
            "Content-Disposition": f"attachment; filename={document_id}.{mime_type.split('/')[1]}",
            "Authorization": "",
        }
    )


def get_exports():
    documents = [export.to_response_dict() for export in DOCUMENT_DB.get_exports()]
    return jsonify(documents)
