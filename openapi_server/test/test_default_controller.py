# coding: utf-8

from __future__ import absolute_import
import unittest

from flask import json
from six import BytesIO

from openapi_server.models.documents import Documents  # noqa: E501
from openapi_server.models.expenses import Expenses  # noqa: E501
from openapi_server.test import BaseTestCase


class TestDefaultController(BaseTestCase):
    """DefaultController integration test stubs"""

    @unittest.skip("multipart/form-data not supported by Connexion")
    def test_addattachments(self):
        """Test case for addattachments

        Upload an attachment for your expenses
        """
        headers = { 
            'Content-Type': 'multipart/form-data',
            'Authorization': 'Bearer special-key',
        }
        data = dict(image=(BytesIO(b'some file data'), 'file.txt'))
        response = self.client.open(
            '/expenses/attachments',
            method='POST',
            headers=headers,
            data=data,
            content_type='multipart/form-data')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    @unittest.skip("*/* not supported by Connexion. Use application/json instead. See https://github.com/zalando/connexion/pull/760")
    def test_adddocument(self):
        """Test case for adddocument

        Make new document
        """
        documents = {}
        headers = { 
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/expenses/documents',
            method='POST',
            headers=headers,
            data=json.dumps(documents),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    @unittest.skip("application/x-www-form-urlencoded not supported by Connexion")
    def test_addexpenses(self):
        """Test case for addexpenses

        Make expense
        """
        headers = { 
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Bearer special-key',
        }
        data = dict(ammount=3.4,
                    cost_type='cost_type_example',
                    note='note_example')
        response = self.client.open(
            '/expenses',
            method='POST',
            headers=headers,
            data=data,
            content_type='application/x-www-form-urlencoded')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_deleteattachmentsbyid(self):
        """Test case for deleteattachmentsbyid

        Delete an attachment by attachment id
        """
        headers = { 
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/expenses/attachments/{attachment_id}'.format(attachment_id=56),
            method='DELETE',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_getallexpenses(self):
        """Test case for getallexpenses

        Get all expenses
        """
        headers = { 
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/expenses',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_getattachmentsbyid(self):
        """Test case for getattachmentsbyid

        Get attachment by attachment id
        """
        headers = { 
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/expenses/attachments/{attachment_id}'.format(attachment_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_getdocumentbyid(self):
        """Test case for getdocumentbyid

        Get document by document id
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/expenses/documents/{document_id}'.format(document_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_getexpenses(self):
        """Test case for getexpenses

        Get information from expenses by id
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/expenses/{expense_id}'.format(expense_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_updateattachmentsbyid(self):
        """Test case for updateattachmentsbyid

        Update attachment by attachment id
        """
        headers = { 
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/expenses/attachments/{attachment_id}'.format(attachment_id=56),
            method='PUT',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
