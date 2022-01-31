from connexion import request
from datetime import datetime, timedelta

from api_server.openapi_server.models.expense_data import ExpenseData
from api_server.openapi_server.models.status import Status

from api_server.openapi_server.database.expense import ExpenseDatabase, Expense
from api_server.openapi_server.database.cost_type import CostTypeDatabase, CostType
from api_server.openapi_server.database.attachment import AttachmentDatabase, AttachmentMeta
from api_server.openapi_server.database.expense_journal import ExpenseJournalDatabase, ExpenseJournalEntry

from api_server.openapi_server.controllers.translate_responses import make_response_translated

from flask import jsonify, make_response


EXPENSE_JOURNAL_DB = ExpenseJournalDatabase()
EXPENSE_DB = ExpenseDatabase()
ATTACHMENT_DB = AttachmentDatabase()
COST_TYPE_DB = CostTypeDatabase()


# region Expenses
def create_expense():
    expense_data = ExpenseData.from_dict(request.get_json())
    expense = Expense.from_employee_model(expense_data)

    if datetime(1970, 1, 1) < expense.transaction_date < datetime.today() + timedelta(hours=2):
        EXPENSE_DB.create_expense(expense)
    else:
        return jsonify("Date needs to be between 1970-01-01 and today"), 400


def get_expense(expense_id: int):
    expense = EXPENSE_DB.get_expense(expense_id)

    if not expense:
        return make_response_translated("Declaratie niet gevonden", 404)

    return jsonify(expense.to_response_dict())


def get_expenses_by_employee(employee_id: int):
    expenses = [expense.to_response_dict() for expense in EXPENSE_DB.query_expenses_by_employee(employee_id)]
    return jsonify(expenses)


def update_expense(expense_id: int):
    expense_old = EXPENSE_DB.get_expense(expense_id)
    status_data = Status.from_dict(request.get_json())

    if not expense_old:
        return make_response_translated("Declaratie niet gevonden", 404)

    expense_new = expense_old.update_by_model(status_data)
    expense_journal_entry = ExpenseJournalEntry.generate(expense_old, expense_new)

    EXPENSE_DB.update_expense(expense_id, expense_new)
    EXPENSE_JOURNAL_DB.create_expense_journal_entry(expense_journal_entry)

# endregion


def get_cost_types():
    cost_types = [cost_type.to_response_dict() for cost_type in COST_TYPE_DB.get_cost_types()]
    return jsonify(cost_types)


def get_attachments(expense_id: int):
    return [{
        "content_type": attachment.content_type,
        "name": attachment.name,
        "content": attachment.download()
    } for attachment in ATTACHMENT_DB.query_attachments_by_expense_id(expense_id)]


def delete_attachment(expense_id: int, attachment_name: str):
    ATTACHMENT_DB.delete_attachment(expense_id, attachment_name)
    return make_response("", 200)
