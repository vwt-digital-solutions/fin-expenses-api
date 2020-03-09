# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from openapi_server.models.base_model_ import Model
from openapi_server import util


class Status(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, status=None, creditor_note=None, manager_note=None, amount=None, note=None, cost_type=None, transaction_date=None):  # noqa: E501
        """Status - a model defined in OpenAPI

        :param status: The status of this Status.  # noqa: E501
        :type status: str
        :param creditor_note: The creditor_note of this Status.  # noqa: E501
        :type creditor_note: str
        :param manager_note: The manager_note of this Status.  # noqa: E501
        :type manager_note: str
        :param amount: The amount of this Status.  # noqa: E501
        :type amount: float
        :param note: The note of this Status.  # noqa: E501
        :type note: str
        :param cost_type: The cost_type of this Status.  # noqa: E501
        :type cost_type: str
        :param transaction_date: The transaction_date of this Status.  # noqa: E501
        :type transaction_date: datetime
        """
        self.openapi_types = {
            'status': str,
            'creditor_note': str,
            'manager_note': str,
            'amount': float,
            'note': str,
            'cost_type': str,
            'transaction_date': datetime
        }

        self.attribute_map = {
            'status': 'status',
            'creditor_note': 'creditor_note',
            'manager_note': 'manager_note',
            'amount': 'amount',
            'note': 'note',
            'cost_type': 'cost_type',
            'transaction_date': 'transaction_date'
        }

        self._status = status
        self._creditor_note = creditor_note
        self._manager_note = manager_note
        self._amount = amount
        self._note = note
        self._cost_type = cost_type
        self._transaction_date = transaction_date

    @classmethod
    def from_dict(cls, dikt) -> 'Status':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The Status of this Status.  # noqa: E501
        :rtype: Status
        """
        return util.deserialize_model(dikt, cls)

    @property
    def status(self):
        """Gets the status of this Status.


        :return: The status of this Status.
        :rtype: str
        """
        return self._status

    @status.setter
    def status(self, status):
        """Sets the status of this Status.


        :param status: The status of this Status.
        :type status: str
        """
        allowed_values = ["draft", "ready_for_creditor", "ready_for_manager", "rejected_by_manager", "rejected_by_creditor", "exported", "cancelled", "approved"]  # noqa: E501
        if status not in allowed_values:
            raise ValueError(
                "Invalid value for `status` ({0}), must be one of {1}"
                .format(status, allowed_values)
            )

        self._status = status

    @property
    def creditor_note(self):
        """Gets the creditor_note of this Status.


        :return: The creditor_note of this Status.
        :rtype: str
        """
        return self._creditor_note

    @creditor_note.setter
    def creditor_note(self, creditor_note):
        """Sets the creditor_note of this Status.


        :param creditor_note: The creditor_note of this Status.
        :type creditor_note: str
        """

        self._creditor_note = creditor_note

    @property
    def manager_note(self):
        """Gets the manager_note of this Status.


        :return: The manager_note of this Status.
        :rtype: str
        """
        return self._manager_note

    @manager_note.setter
    def manager_note(self, manager_note):
        """Sets the manager_note of this Status.


        :param manager_note: The manager_note of this Status.
        :type manager_note: str
        """

        self._manager_note = manager_note

    @property
    def amount(self):
        """Gets the amount of this Status.


        :return: The amount of this Status.
        :rtype: float
        """
        return self._amount

    @amount.setter
    def amount(self, amount):
        """Sets the amount of this Status.


        :param amount: The amount of this Status.
        :type amount: float
        """
        if amount is not None and amount < 0.01:  # noqa: E501
            raise ValueError("Invalid value for `amount`, must be a value greater than or equal to `0.01`")  # noqa: E501

        self._amount = amount

    @property
    def note(self):
        """Gets the note of this Status.


        :return: The note of this Status.
        :rtype: str
        """
        return self._note

    @note.setter
    def note(self, note):
        """Sets the note of this Status.


        :param note: The note of this Status.
        :type note: str
        """

        self._note = note

    @property
    def cost_type(self):
        """Gets the cost_type of this Status.


        :return: The cost_type of this Status.
        :rtype: str
        """
        return self._cost_type

    @cost_type.setter
    def cost_type(self, cost_type):
        """Sets the cost_type of this Status.


        :param cost_type: The cost_type of this Status.
        :type cost_type: str
        """

        self._cost_type = cost_type

    @property
    def transaction_date(self):
        """Gets the transaction_date of this Status.


        :return: The transaction_date of this Status.
        :rtype: datetime
        """
        return self._transaction_date

    @transaction_date.setter
    def transaction_date(self, transaction_date):
        """Sets the transaction_date of this Status.


        :param transaction_date: The transaction_date of this Status.
        :type transaction_date: datetime
        """

        self._transaction_date = transaction_date
