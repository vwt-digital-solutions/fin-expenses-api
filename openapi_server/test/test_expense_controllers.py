# coding: utf-8

from __future__ import absolute_import

import config
import json
import unittest

import adal

from openapi_server.test import BaseTestCase


class TestExpenseControllers(BaseTestCase):
    """ Test Expense Controllers """

    def get_token(self):
        """
        Create a token for testing
        :return:
        """
        oauth_expected_authenticator = config.OAUTH_EXPECTED_AUTHENTICATOR
        client_id = config.OAUTH_CLIENT_ID
        client_secret = config.OAUTH_CLIENT_SECRET

        resource = 'https://management.core.windows.net/'

        # get an Azure access token using the adal library
        context = adal.AuthenticationContext(oauth_expected_authenticator)
        token_response = context.acquire_token_with_client_credentials(resource, client_id, client_secret)

        access_token = token_response.get('accessToken')
        return access_token

    def test_add_expenses(self):
        """
        Test case for add_expenses
        Make an expense
        """
        access_token = self.get_token()
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }

        expense_data = dict(
            amount=3.4,
            cost_type='cost_type_example:00000',
            note='note_example',
            date_of_transaction="2019-07-11"
        )

        response = self.client.open(
            '/employees/expenses',
            method='POST',
            headers=headers,
            data=json.dumps(expense_data),
            content_type='application/json')
        self.assertEqual(response.status_code, 201)

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


if __name__ == '__main__':
    unittest.main()
