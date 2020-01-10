# coding: utf-8

from __future__ import absolute_import
import unittest

from flask import json
from six import BytesIO

from openapi_server.models.attachment_data import AttachmentData  # noqa: E501
from openapi_server.models.booking_file import BookingFile  # noqa: E501
from openapi_server.models.cost_types import CostTypes  # noqa: E501
from openapi_server.models.expense_data import ExpenseData  # noqa: E501
from openapi_server.models.expense_data_array import ExpenseDataArray  # noqa: E501
from openapi_server.models.export_file import ExportFile  # noqa: E501
from openapi_server.models.status import Status  # noqa: E501
from openapi_server.models.url_array import UrlArray  # noqa: E501
from openapi_server.test import BaseTestCase


class TestDefaultController(BaseTestCase):
    """DefaultController integration test stubs"""

    def test_add_attachment_employee(self):
        """Test case for add_attachment_employee

        Get attachments by expense id
        """
        attachment_data = "{\n  \"name\": \"somename\",\n  \"content\": \"b64 string\"\n}"
        headers = { 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/employees/expenses/{expenses_id}/attachments'.format(expenses_id=56),
            method='POST',
            headers=headers,
            data=json.dumps(attachment_data),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_add_expense(self):
        """Test case for add_expense

        Make expense
        """
        expense_data = "{\n    \"note\": \"This is a note\",\n    \"id\": \"R1rt2345\",\n    \"amount\": 45.56,\n    \"cost_type\": \"Office Utilities\",\n    \"transaction_date\": \"2017-07-21T17:32:28Z\"\n}"
        headers = { 
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/employees/expenses',
            method='POST',
            headers=headers,
            data=json.dumps(expense_data),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_create_booking_and_payment_file(self):
        """Test case for create_booking_and_payment_file

        Creates a single booking and payment document containing all expenses ready for payment.
        """
        headers = { 
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/finances/documents',
            method='POST',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_delete_attachment(self):
        """Test case for delete_attachment

        Delete attachment by expense id and attachment name
        """
        headers = { 
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/employees/expenses/{expenses_id}/attachments/{attachments_name}'.format(expenses_id=56, attachments_name='attachments_name_example'),
            method='DELETE',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_all_creditor_expenses(self):
        """Test case for get_all_creditor_expenses

        Get all expenses
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/finances/expenses',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_attachment_controllers(self):
        """Test case for get_attachment_controllers

        Get attachments by expense id
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/controllers/expenses/{expenses_id}/attachments'.format(expenses_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_attachment_creditor(self):
        """Test case for get_attachment_creditor

        Get attachments by expense id
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/finances/expenses/{expenses_id}/attachments'.format(expenses_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_attachment_employee(self):
        """Test case for get_attachment_employee

        Get attachments by expense id
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/employees/expenses/{expenses_id}/attachments'.format(expenses_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_attachment_manager(self):
        """Test case for get_attachment_manager

        Get attachments by expense id
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/managers/expenses/{expenses_id}/attachments'.format(expenses_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_controller_expenses(self):
        """Test case for get_controller_expenses

        Get all expenses
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/controllers/expenses',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_cost_types(self):
        """Test case for get_cost_types

        Get all cost_types
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/employees/cost-types',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_document(self):
        """Test case for get_document

        Returns a CSV => of a booking file or XML => of payment file
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/finances/expenses/documents/{document_id}/kinds/{document_type}'.format(document_id='document_id_example', document_type='document_type_example'),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_document_list(self):
        """Test case for get_document_list

        Get a list of all booking and payment files
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/finances/documents',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_employee_expenses(self):
        """Test case for get_employee_expenses

        Get all expenses belonging to a specific logged in employee
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/employees/{employee_id}/expenses'.format(employee_id='employee_id_example'),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_expenses_creditor(self):
        """Test case for get_expenses_creditor

        Get information from expenses by id
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/finances/expenses/{expenses_id}'.format(expenses_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_expenses_employee(self):
        """Test case for get_expenses_employee

        Get information from expenses by id
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/employees/expenses/{expenses_id}'.format(expenses_id=56),
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_export_expenses(self):
        """Test case for get_export_expenses

        Get csv with all expenses
        """
        query_string = [('expenses_list', 'expenses')]
        headers = { 
            'Accept': 'text/csv',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/finances/expenses/export',
            method='GET',
            headers=headers,
            query_string=query_string)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_get_managers_expenses(self):
        """Test case for get_managers_expenses

        Get all expenses for approval of a specific manager
        """
        headers = { 
            'Accept': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/managers/expenses',
            method='GET',
            headers=headers)
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_update_expenses_creditor(self):
        """Test case for update_expenses_creditor

        Update expense
        """
        status = {
  "status" : "rejected_by_creditor",
  "finance_note" : "Wrong amount"
}
        headers = { 
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/finances/expenses/{expenses_id}'.format(expenses_id=56),
            method='PUT',
            headers=headers,
            data=json.dumps(status),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_update_expenses_employee(self):
        """Test case for update_expenses_employee

        Update expense
        """
        status = {
  "status" : "rejected_by_creditor",
  "finance_note" : "Wrong amount"
}
        headers = { 
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/employees/expenses/{expenses_id}'.format(expenses_id=56),
            method='PUT',
            headers=headers,
            data=json.dumps(status),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))

    def test_update_expenses_manager(self):
        """Test case for update_expenses_manager

        Update expense
        """
        status = {
  "status" : "rejected_by_creditor",
  "finance_note" : "Wrong amount"
}
        headers = { 
            'Content-Type': 'application/json',
            'Authorization': 'Bearer special-key',
        }
        response = self.client.open(
            '/managers/expenses/{expenses_id}'.format(expenses_id=56),
            method='PUT',
            headers=headers,
            data=json.dumps(status),
            content_type='application/json')
        self.assert200(response,
                       'Response body is : ' + response.data.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
