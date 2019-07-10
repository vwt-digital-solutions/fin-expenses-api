import connexion
from flask import make_response, jsonify
from google.cloud import datastore

from openapi_server.models.documents import Documents
from openapi_server.models.expenses import Expenses
from openapi_server.models.form_data import FormData
from openapi_server.models.image import Image


class ClaimExpenses:
    """
    Class based function to house all Expenses functionality

    """

    def __init__(self):
        self.db_client = datastore.Client()
        self.request = connexion.request

    def get_expenses(self, expenses_id):
        """Get expenses with expense_id"""

        expenses_info = self.db_client.query(kind='Expenses')
        expenses_key = self.db_client.key('Expenses', expenses_id)
        expenses_info.key_filter(expenses_key, '=')
        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = [{
                'amount': ed['amount'],
                'note': ed['note']
            } for ed in expenses_data]
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)

    def get_all_expenses(self):
        """Get JSON of all the expenses"""

        expenses_info = self.db_client.query(kind='Expenses')
        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = [{
                'amount': ed['amount'],
                'note': ed['note']
            } for ed in expenses_data]
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)

    def add_expenses(self, data):
        """Add expense with given data amount and given data note"""

        key = self.db_client.key('Expenses')
        entity = datastore.Entity(key=key)
        entity.update({
            'amount': data.amount,
            'note': data.note
        })
        self.db_client.put(entity)
        return make_response(jsonify(entity.key.id_or_name), 201)


expense_instance = ClaimExpenses()


def add_attachment():  # noqa: E501
    """Upload an attachment for your expenses

     # noqa: E501

    :param image:
    :type image: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        image = Image.from_dict(connexion.request.get_json())  # noqa: E501
    return 'do some magic!'


def add_document():  # noqa: E501
    """Make new document

     # noqa: E501

    :param documents:
    :type documents: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        documents = Documents.from_dict(connexion.request.get_json())  # noqa: E501
    return 'do some magic!'


def add_expense():  # noqa: E501
    """Make expense

     # noqa: E501

    :param form_data:
    :type form_data: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        form_data = FormData.from_dict(connexion.request.get_json())  # noqa: E501
    return expense_instance.add_expenses(form_data)


def delete_attachments_by_id():  # noqa: E501
    """Delete an attachment by attachment id

     # noqa: E501


    :rtype: None
    """
    return 'do some magic!'


def get_all_expenses():  # noqa: E501
    """Get all expenses

     # noqa: E501


    :rtype: None
    """
    return expense_instance.get_all_expenses()


def get_attachments_by_id():  # noqa: E501
    """Get attachment by attachment id

     # noqa: E501


    :rtype: None
    """
    return 'do some magic!'


def get_document_by_id():  # noqa: E501
    """Get document by document id

     # noqa: E501


    :rtype: Documents
    """
    return 'do some magic!'


def get_expenses(expenses_id):  # noqa: E501
    """Get information from expenses by id

     # noqa: E501


    :rtype: Expenses
    """
    return expense_instance.get_expenses(expenses_id)


def update_attachments_by_id():  # noqa: E501
    """Update attachment by attachment id

     # noqa: E501


    :rtype: None
    """
    return 'do some magic!'
