# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from openapi_server.models.base_model_ import Model
from openapi_server import util

from openapi_server.models.expense_data_flags import ExpenseDataFlags  # noqa: E501
import re  # noqa: E501


class ExpenseData(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, amount=None, note=None, cost_type=None, transaction_date=None, flags=None):  # noqa: E501
        """ExpenseData - a model defined in OpenAPI

        :param amount: The amount of this ExpenseData.  # noqa: E501
        :type amount: float
        :param note: The note of this ExpenseData.  # noqa: E501
        :type note: str
        :param cost_type: The cost_type of this ExpenseData.  # noqa: E501
        :type cost_type: str
        :param transaction_date: The transaction_date of this ExpenseData.  # noqa: E501
        :type transaction_date: str
        :param flags: The flags of this ExpenseData.  # noqa: E501
        :type flags: ExpenseDataFlags
        """
        self.openapi_types = {
            'amount': float,
            'note': str,
            'cost_type': str,
            'transaction_date': str,
            'flags': ExpenseDataFlags
        }

        self.attribute_map = {
            'amount': 'amount',
            'note': 'note',
            'cost_type': 'cost_type',
            'transaction_date': 'transaction_date',
            'flags': 'flags'
        }

        self._amount = amount
        self._note = note
        self._cost_type = cost_type
        self._transaction_date = transaction_date
        self._flags = flags

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
        if amount is not None and amount < 0.01:  # noqa: E501
            raise ValueError("Invalid value for `amount`, must be a value greater than or equal to `0.01`")  # noqa: E501

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
    def transaction_date(self):
        """Gets the transaction_date of this ExpenseData.


        :return: The transaction_date of this ExpenseData.
        :rtype: str
        """
        return self._transaction_date

    @transaction_date.setter
    def transaction_date(self, transaction_date):
        """Sets the transaction_date of this ExpenseData.


        :param transaction_date: The transaction_date of this ExpenseData.
        :type transaction_date: str
        """
        if transaction_date is None:
            raise ValueError("Invalid value for `transaction_date`, must not be `None`")  # noqa: E501
        if transaction_date is not None and not re.search(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3})Z$', transaction_date):  # noqa: E501
            raise ValueError("Invalid value for `transaction_date`, must be a follow pattern or equal to `/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}.\d{3})Z$/`")  # noqa: E501

        self._transaction_date = transaction_date

    @property
    def flags(self):
        """Gets the flags of this ExpenseData.


        :return: The flags of this ExpenseData.
        :rtype: ExpenseDataFlags
        """
        return self._flags

    @flags.setter
    def flags(self, flags):
        """Sets the flags of this ExpenseData.


        :param flags: The flags of this ExpenseData.
        :type flags: ExpenseDataFlags
        """

        self._flags = flags
