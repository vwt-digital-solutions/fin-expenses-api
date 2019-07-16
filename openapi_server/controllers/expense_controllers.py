import datetime
import config
from jwkaas import JWKaas

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

    def __init__(self, expected_audience, expected_issuer, jwks_url):
        self.db_client = datastore.Client()
        self.request = connexion.request
        self.employee_info = dict()
        self.expected_audience = expected_audience
        self.expected_issuer = expected_issuer
        self.jwks_url = jwks_url

    def get_employee_info(self):
        """
        Get all available information about the employee
        :return:
        """
        my_jwkaas = None
        if hasattr(config, "OAUTH_JWKS_URL"):
            my_jwkaas = JWKaas(
                self.expected_audience, self.expected_issuer, jwks_url=self.jwks_url
            )
        token = self.request.environ["HTTP_AUTHORIZATION"]
        self.employee_info = {**my_jwkaas.get_connexion_token_info(token.split(" ")[1])}

    def get_expenses(self, expenses_id):
        """Get expenses with expense_id"""

        expenses_info = self.db_client.query(kind="Expenses")
        expenses_key = self.db_client.key("Expenses", expenses_id)
        expenses_info.key_filter(expenses_key, "=")
        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = [
                {"amount": ed["amount"], "note": ed["note"], "cost_type": ed["cost_type"]} for ed in expenses_data
            ]
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)

    def get_all_expenses(self):
        """Get JSON of all the expenses"""

        expenses_info = self.db_client.query(kind="Expenses")
        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = [
                {
                    "amount": ed["amount"],
                    "note": ed["note"],
                    "cost_type": ed["cost_type"],
                    "date_of_claim": ed["date_of_claim"],
                    "date_of_transaction": ed["date_of_transaction"],
                    "employee": ed["employee"],
                }
                for ed in expenses_data
            ]
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)

    def add_expenses(self, data):
        """Add expense with given data amount and given data note"""
        self.get_employee_info()
        key = self.db_client.key("Expenses")
        entity = datastore.Entity(key=key)
        entity.update(
            {
                "employee": dict(
                    email=self.employee_info["unique_name"],
                    family_name=self.employee_info["family_name"],
                    given_name=self.employee_info["given_name"],
                    full_name=self.employee_info["name"],
                ),
                "amount": data.amount,
                "note": data.note,
                "cost_type": data.cost_type,
                "date_of_transaction": data.date_of_transaction,
                "date_of_claim": datetime.datetime.now().isoformat(timespec='seconds'),
            }
        )
        self.db_client.put(entity)
        return make_response(jsonify(entity.key.id_or_name), 201)


expense_instance = ClaimExpenses(
    expected_audience=config.OAUTH_EXPECTED_AUDIENCE,
    expected_issuer=config.OAUTH_EXPECTED_ISSUER,
    jwks_url=config.OAUTH_JWKS_URL,
)


def add_attachment():  # noqa: E501
    """Upload an attachment for your expenses

     # noqa: E501

    :param image:
    :type image: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        image = Image.from_dict(connexion.request.get_json())  # noqa: E501
    return "do some magic!"


def add_document():  # noqa: E501
    """Make new document

     # noqa: E501

    :param documents:
    :type documents: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        documents = Documents.from_dict(connexion.request.get_json())  # noqa: E501
    return "do some magic!"


def add_expense():  # noqa: E501
    """Make expense

     # noqa: E501

    :param form_data:
    :type form_data: dict | bytes

    :rtype: None
    """
    try:
        if connexion.request.is_json:
            form_data = FormData.from_dict(connexion.request.get_json())  # noqa: E501
            return expense_instance.add_expenses(form_data)
    except Exception as er:
        return jsonify({f'Error: {er}'})


def delete_attachments_by_id():  # noqa: E501
    """Delete an attachment by attachment id

     # noqa: E501


    :rtype: None
    """
    return "do some magic!"


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
    return "do some magic!"


def get_document_by_id():  # noqa: E501
    """Get document by document id

     # noqa: E501


    :rtype: Documents
    """
    return "do some magic!"


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
    return "do some magic!"


def make_bookingfile(expenses_id):  # noqa: E501
    """Make a booking file based of expenses id

     # noqa: E501


    :rtype: None
    """
    return "do some magic!"
