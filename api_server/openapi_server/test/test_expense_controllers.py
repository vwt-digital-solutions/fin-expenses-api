# coding: utf-8

from __future__ import absolute_import

import config
import unittest

import adal

from openapi_server.test import BaseTestCase


def get_token():
    """
    Create a token for testing
    :return:
    """
    oauth_expected_authenticator = config.OAUTH_EXPECTED_AUTHENTICATOR
    client_id = config.OAUTH_E2E_APPID
    client_secret = config.OAUTH_E2E_APPSECRET
    resource = config.OAUTH_E2E_EXPECTED_AUDIENCE

    # get an Azure access token using the adal library
    context = adal.AuthenticationContext(oauth_expected_authenticator)
    token_response = context.acquire_token_with_client_credentials(resource, client_id, client_secret)

    access_token = token_response.get('accessToken')
    return access_token


class TestExpenseControllers(BaseTestCase):
    """ Test Expense Controllers """

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


if __name__ == '__main__':
    unittest.main()
