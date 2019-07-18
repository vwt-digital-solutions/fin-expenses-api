# coding: utf-8

from __future__ import absolute_import

from openapi_server.models.base_model_ import Model
from openapi_server import util


class CostTypes(Model):
    """NOTE: This class is auto generated by OpenAPI Generator (https://openapi-generator.tech).

    Do not edit the class manually.
    """

    def __init__(self, cid=None, ctype=None):  # noqa: E501
        """CostTypes - a model defined in OpenAPI

        :param cid: The cid of this CostTypes.  # noqa: E501
        :type cid: int
        :param ctype: The ctype of this CostTypes.  # noqa: E501
        :type ctype: str
        """
        self.openapi_types = {
            'cid': int,
            'ctype': str,
        }

        self.attribute_map = {
            'cid': 'cid',
            'ctype': 'ctype',
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
    def ctype(self):
        """Gets the ctype of this costtypes.


        :return: The ctype of this costtypes.
        :rtype: str
        """
        return self._ctype

    @ctype.setter
    def ctype(self, ctype):
        """Sets the ctype of this costtypes.


        :param ctype: The ctype of this costtypes.
        :type ctype: str
        """

        self._ctype = ctype

    @property
    def cid(self):
        """Gets the cid of this costtypes.


        :return: The cid of this costtypes.
        :rtype: str
        """
        return self._cid

    @cid.setter
    def cid(self, cid):
        """Sets the cid of this costtypes.


        :param cid: The cid of this costtypes.
        :type cid: str
        """

        self._cid = cid