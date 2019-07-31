# coding: utf-8

from __future__ import absolute_import

import json
import unittest

from openapi_server.test import BaseTestCase


class TestExpenseControllers(BaseTestCase):
    """ Test Expense Controllers """

    def test_get_expense(self):
        """Test case for get expense"""

        headers = {
            'Content-Type': 'application/json',
        }
        response = self.client.open(
            '/employees/expenses/5635703144710134',
            method='GET',
            headers=headers,
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_all_expense(self):
        """Test case for get all expense"""

        headers = {
            'Content-Type': 'application/json',
        }
        response = self.client.open(
            '/employees/expenses',
            method='GET',
            headers=headers,
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_add_expense(self):
        """Test case for addexpenses

        Make expense
        """
        data = dict(amount=3.4,
                    note='note_example')

        response = self.client.open(
            '/employees/expenses',
            method='POST',
            data=json.dumps(data),
            content_type='application/json')
        self.assertEqual(response.status_code, 201)


if __name__ == '__main__':
    unittest.main()
