# coding: utf-8

from __future__ import absolute_import

from openapi_server.models.base_model_ import Model
from openapi_server import util


class ExpenseData(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, amount=None, note=None, cost_type=None, date_of_transaction=None):  # noqa: E501
        """ExpenseData - a model defined in OpenAPI

        :param amount: The amount of this ExpenseData.  # noqa: E501
        :type amount: float
        :param note: The note of this ExpenseData.  # noqa: E501
        :type note: str
        :param cost_type: The cost_type of this ExpenseData.  # noqa: E501
        :type cost_type: str
        :param date_of_transaction: The date_of_transaction of this ExpenseData.  # noqa: E501
        :type date_of_transaction: str
        """
        self.openapi_types = {
            'amount': float,
            'note': str,
            'cost_type': str,
            'date_of_transaction': str
        }

        self.attribute_map = {
            'amount': 'amount',
            'note': 'note',
            'cost_type': 'cost_type',
            'date_of_transaction': 'date_of_transaction'
        }

        self._amount = amount
        self._note = note
        self._cost_type = cost_type
        self._date_of_transaction = date_of_transaction

    @classmethod
    def from_dict(cls, dikt) -> 'ExpenseData':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The ExpenseData of this ExpenseData.  # noqa: E501
        :rtype: ExpenseData
        """
        return util.deserialize_model(dikt, cls)

    @property
    def amount(self):
        """Gets the amount of this ExpenseData.


        :return: The amount of this ExpenseData.
        :rtype: float
        """
        return self._amount

    @amount.setter
    def amount(self, amount):
        """Sets the amount of this ExpenseData.


        :param amount: The amount of this ExpenseData.
        :type amount: float
        """
        if amount is None:
            raise ValueError("Invalid value for `amount`, must not be `None`")  # noqa: E501

        self._amount = amount

    @property
    def note(self):
        """Gets the note of this ExpenseData.


        :return: The note of this ExpenseData.
        :rtype: str
        """
        return self._note

    @note.setter
    def note(self, note):
        """Sets the note of this ExpenseData.


        :param note: The note of this ExpenseData.
        :type note: str
        """
        if note is None:
            raise ValueError("Invalid value for `note`, must not be `None`")  # noqa: E501

        self._note = note

    @property
    def cost_type(self):
        """Gets the cost_type of this ExpenseData.


        :return: The cost_type of this ExpenseData.
        :rtype: str
        """
        return self._cost_type

    @cost_type.setter
    def cost_type(self, cost_type):
        """Sets the cost_type of this ExpenseData.


        :param cost_type: The cost_type of this ExpenseData.
        :type cost_type: str
        """
        if cost_type is None:
            raise ValueError("Invalid value for `cost_type`, must not be `None`")  # noqa: E501

        self._cost_type = cost_type

    @property
    def date_of_transaction(self):
        """Gets the date_of_transaction of this ExpenseData.


        :return: The date_of_transaction of this ExpenseData.
        :rtype: str
        """
        return self._date_of_transaction

    @date_of_transaction.setter
    def date_of_transaction(self, date_of_transaction):
        """Sets the date_of_transaction of this ExpenseData.


        :param date_of_transaction: The date_of_transaction of this ExpenseData.
        :type date_of_transaction: str
        """
        if date_of_transaction is None:
            raise ValueError("Invalid value for `date_of_transaction`, must not be `None`")  # noqa: E501

        self._date_of_transaction = date_of_transaction
