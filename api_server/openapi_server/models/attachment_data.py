# coding: utf-8

from __future__ import absolute_import

from openapi_server.models.base_model_ import Model
from openapi_server import util


class AttachmentData(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, name=None, mime_type=None, content=None):  # noqa: E501
        """ExpenseData - a model defined in OpenAPI

        """
        self.openapi_types = {
            'name': str,
            'mime_type': str,
            'content': str
        }

        self.attribute_map = {
            'name': 'name',
            'mime_type': 'mime_type',
            'content': 'content'
        }

        self._name = name
        self._mime_type = mime_type
        self._content = content

    @classmethod
    def from_dict(cls, dikt) -> 'AttachmentData':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The ExpenseData of this ExpenseData.  # noqa: E501
        :rtype: ExpenseData
        """
        return util.deserialize_model(dikt, cls)

    @property
    def name(self):
        """Gets the name of this ExpenseData.


        :return: The name of this ExpenseData.
        :rtype: float
        """
        return self._name

    @name.setter
    def name(self, name):
        """Sets the name of this ExpenseData.


        :param name: The name of this ExpenseData.
        :type name: float
        """
        if name is None:
            raise ValueError("Invalid value for `name`, must not be `None`")  # noqa: E501

        self._name = name

    @property
    def mime_type(self):
        """Gets the mime_type of this ExpenseData.


        :return: The mime_type of this ExpenseData.
        :rtype: str
        """
        return self._mime_type

    @mime_type.setter
    def mime_type(self, mime_type):
        """Sets the mime_type of this ExpenseData.


        :param mime_type: The mime_type of this ExpenseData.
        :type mime_type: str
        """
        if mime_type is None:
            raise ValueError("Invalid value for `mime_type`, must not be `None`")  # noqa: E501

        self._mime_type = mime_type

    @property
    def content(self):
        """Gets the content of this ExpenseData


        :param content: The content of this ExpenseData.
        :type content: str"""
        return self._content

    @content.setter
    def content(self, content):
        """Sets the content of this ExpenseData"""

        if content is None:
            raise ValueError("Invalid value for `content`, must not be `None`")  # noqa: E501

        self._content = content
