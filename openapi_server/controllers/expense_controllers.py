import connexion

from openapi_server.models.documents import Documents  # noqa: E501
from openapi_server.models.expenses import Expenses  # noqa: E501
from openapi_server.models.form_data import FormData  # noqa: E501
from openapi_server.models.image import Image  # noqa: E501


class ClaimExpenses:
    """
    Class based function to house all Expenses functionality
    """
    
    def __init__(self, something):
        self.something = something
    

expense_instance = ClaimExpenses(something='Something')


def add_attachment(image):  # noqa: E501
    """Upload an attachment for your expenses

     # noqa: E501

    :param image: 
    :type image: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        image = Image.from_dict(connexion.request.get_json())  # noqa: E501
    return 'do some magic!'


def add_document(documents):  # noqa: E501
    """Make new document

     # noqa: E501

    :param documents: 
    :type documents: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        documents = Documents.from_dict(connexion.request.get_json())  # noqa: E501
    return 'do some magic!'


def add_expense(form_data):  # noqa: E501
    """Make expense

     # noqa: E501

    :param form_data: 
    :type form_data: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        form_data = FormData.from_dict(connexion.request.get_json())  # noqa: E501
    return 'do some magic!'


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
    return 'do some magic!'


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


def get_expenses():  # noqa: E501
    """Get information from expenses by id

     # noqa: E501


    :rtype: Expenses
    """
    return 'do some magic!'


def update_attachments_by_id():  # noqa: E501
    """Update attachment by attachment id

     # noqa: E501


    :rtype: None
    """
    return 'do some magic!'
