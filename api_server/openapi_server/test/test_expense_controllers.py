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
            amount=6.4,
            cost_type='Kantoorbenodigdheden:412000',
            note='Scharen en potloden',
            date_of_transaction=1564963200,
            attachment="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z/C/HgAGgwJ/l"
                       "K3Q6wAAAABJRU5ErkJggg==.data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAD"
                       "UlEQVR42mP8z/C/HgAGgwJ/lK3Q6wAAAABJRU5ErkJggg=="
        )

        response = self.client.open(
            '/employees/expenses',
            method='POST',
            headers=headers,
            data=json.dumps(expense_data),
            content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_update_expense(self):
        """
        Test case for updating the expense
        :return:
        """
        access_token = get_token()
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }

        post_data = dict(
            status="cancelled_by_creditor",
            finance_note="Wrong amount",
            amount=21,
            cost_type="Software:415020",
            date_of_transaction=1564963200
        )
        expenses_id = '5713912150360064'

        response = self.client.open(
            f'/finances/expenses/{expenses_id}',
            method='PUT',
            headers=headers,
            data=json.dumps(post_data),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

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

        query_string = [('name', '8_19_11:22:31-19082019.csv')]
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

    def test_get_attachment(self):
        """Test case for get_attachment

        Get attachment
        """
        access_token = get_token()
        headers = {
            'Authorization': f'Bearer {access_token}',
        }

        expenses_id = '5713912150360064'
        response = self.client.open(
            f'/finances/expenses/{expenses_id}/attachments',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_cost_types(self):
        """Test case for get_cost_types

        Get all cost_types
        """
        access_token = get_token()
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}',
        }
        response = self.client.open(
            '/employees/cost-types',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_booking_document(self):
        """Test case for get_document

        Returns a CSV => of a booking file or XML => of payment file
        """
        access_token = get_token()
        headers = {
            'Accept': 'text/csv',
            'Authorization': f'Bearer {access_token}',
        }

        document_type = 'booking_file'
        document_date = '8_19_11:22:31-19082019.csv'
        response = self.client.open(
            f'/finances/expenses/documents/{document_date}/kinds/{document_type}',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_payment_document(self):
        """Test case for get_document

        Returns a CSV => of a booking file or XML => of payment file
        """
        access_token = get_token()

        headers = {
            'Accept': 'application/xml',
            'Authorization': f'Bearer {access_token}',

        }
        document_type = 'payment_file'
        document_date = '8_19_11:22:31-19082019'
        response = self.client.open(
            f'/finances/expenses/documents/{document_date}/kinds/{document_type}',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
