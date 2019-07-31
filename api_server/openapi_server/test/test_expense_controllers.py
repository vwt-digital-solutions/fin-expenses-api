# coding: utf-8

from __future__ import absolute_import

import config
import json
import unittest

import adal

from openapi_server.test import BaseTestCase


def get_token():
    """
    Create a token for testing
    :return:
    """
    oauth_expected_authenticator = config.OAUTH_EXPECTED_AUTHENTICATOR
    client_id = config.OAUTH_CLIENT_ID
    client_secret = config.OAUTH_CLIENT_SECRET
    resource = config.OAUTH_EXPECTED_AUDIENCE

    # get an Azure access token using the adal library
    context = adal.AuthenticationContext(oauth_expected_authenticator)
    token_response = context.acquire_token_with_client_credentials(resource, client_id, client_secret)

    access_token = token_response.get('accessToken')
    return access_token


class TestExpenseControllers(BaseTestCase):
    """ Test Expense Controllers """

    def test_add_expenses(self):
        """
        Test case for add_expenses
        Make an expense
        """
        access_token = get_token()
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }

        expense_data = dict(
            amount=3.4,
            cost_type='cost_type_example:00000',
            note='note_example',
            date_of_transaction="2019-07-11",
            attachment="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z/C/HgAGgwJ/l"
                       "K3Q6wAAAABJRU5ErkJggg=="
        )

        response = self.client.open(
            '/employees/expenses',
            method='POST',
            headers=headers,
            data=json.dumps(expense_data),
            content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_create_booking_document(self):
        """Test case for create_booking_document

        Creates a single booking document
        """
        access_token = get_token()

        query_string = [('name', '')]
        document_type = 'booking_file'
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        response = self.client.open(
            f'/finances/expenses/{document_type}/files',
            method='POST',
            headers=headers,
            query_string=query_string)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_create_payment_document(self):
        """Test case for create_document

        Creates a single booking or payment document
        """
        access_token = get_token()

        query_string = [('name', '7_31_13:39:17-31072019.csv')]
        document_type = 'payment_file'
        headers = {
            'Authorization': f'Bearer {access_token}',
        }
        response = self.client.open(
            f'/finances/expenses/{document_type}/files',
            method='POST',
            headers=headers,
            query_string=query_string)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
