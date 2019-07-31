# coding: utf-8

from __future__ import absolute_import
from datetime import date, datetime  # noqa: F401

from typing import List, Dict  # noqa: F401

from openapi_server.models.base_model_ import Model
from openapi_server import util


class CostTypes(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, cid=None, ctype=None):  # noqa: E501
        """CostTypes - a model defined in OpenAPI

        :param cid: The cid of this CostTypes.  # noqa: E501
        :type cid: str
        :param ctype: The ctype of this CostTypes.  # noqa: E501
        :type ctype: str
        """
        self.openapi_types = {
            'cid': str,
            'ctype': str
        }

        self.attribute_map = {
            'cid': 'cid',
            'ctype': 'ctype'
        }

        self._cid = cid
        self._ctype = ctype

    @classmethod
    def from_dict(cls, dikt) -> 'CostTypes':
        """Returns the dict as a model

        :param dikt: A dict.
        :type: dict
        :return: The CostTypes of this CostTypes.  # noqa: E501
        :rtype: CostTypes
        """
        return util.deserialize_model(dikt, cls)

    @property
    def cid(self):
        """Gets the cid of this CostTypes.

        A cost type doel organisation code  # noqa: E501

        :return: The cid of this CostTypes.
        :rtype: str
        """
        return self._cid

    @cid.setter
    def cid(self, cid):
        """Sets the cid of this CostTypes.

        A cost type doel organisation code  # noqa: E501

        :param cid: The cid of this CostTypes.
        :type cid: str
        """
        if cid is None:
            raise ValueError("Invalid value for `cid`, must not be `None`")  # noqa: E501

        self._cid = cid

    @property
    def ctype(self):
        """Gets the ctype of this CostTypes.


        :return: The ctype of this CostTypes.
        :rtype: str
        """
        return self._ctype

    @ctype.setter
    def ctype(self, ctype):
        """Sets the ctype of this CostTypes.


        :param ctype: The ctype of this CostTypes.
        :type ctype: str
        """
        if ctype is None:
            raise ValueError("Invalid value for `ctype`, must not be `None`")  # noqa: E501

        self._ctype = ctype
