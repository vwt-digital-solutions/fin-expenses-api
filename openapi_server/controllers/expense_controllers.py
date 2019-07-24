import datetime
import tempfile

import config
from jwkaas import JWKaas
import logging
import pandas as pd

import connexion
from flask import make_response, jsonify, Response, request
from google.cloud import datastore, storage

from openapi_server.models.booking_file import BookingFile
from openapi_server.models.cost_types import CostTypes
from openapi_server.models.documents import Documents
from openapi_server.models.expense_data import ExpenseData
from openapi_server.models.expense_data_array import ExpenseDataArray

logger = logging.getLogger(__name__)

# Constants
MAX_DAYS_RESOLVE = 3
EXPORTABLE_STATUSES = ["payable", "approved", "late_on_approval", "to_be_approved"]


class ClaimExpenses:
    """
    Class based function to house all Expenses functionality

    """

    def __init__(self, expected_audience, expected_issuer, jwks_url):
        self.ds_client = datastore.Client()  # Datastore
        self.cs_client = storage.Client()  # CloudStore
        self.request = connexion.request
        self.employee_info = dict()
        self.expected_audience = expected_audience
        self.expected_issuer = expected_issuer
        self.jwks_url = jwks_url
        self.hashed_email = ""
        self.bucket_name = config.GOOGLE_STORAGE_BUCKET
        self.now = datetime.datetime.now()

    def get_employee_info(self):
        """
        Get all available information about the employee
        :return:
        """
        my_jwkaas = None
        if hasattr(config, "OAUTH_JWKS_URL"):
            my_jwkaas = JWKaas(
                self.expected_audience, self.expected_issuer, jwks_url=self.jwks_url
            )
        token = self.request.environ["HTTP_AUTHORIZATION"]
        self.employee_info = {**my_jwkaas.get_connexion_token_info(token.split(" ")[1])}

    def get_employee_afas_data(self, unique_name):
        """
        Data Access Link to the AFAS environment to retrieve employee information
        - Bank Account
        - Company Code
        - Any other detail we will be needing to complete the payment
        This link is made available through the HR-On boarding project
        :param unique_name: An email address
        """

        employee_afas_key = self.ds_client.key("AFAS_HRM", unique_name)
        employee_afas_query = self.ds_client.get(employee_afas_key)
        if employee_afas_query:
            data = dict(employee_afas_query.items())
            return data
        else:
            return {"Info": f"No detail of {unique_name} found in HRM -AFAS"}

    def get_cost_types(self):
        """
        Get cost types from a CSV file
        :return:
        """

        cost_types = self.ds_client.query(kind="CostTypes")
        results = [
            {"ctype": row["Omschrijving"], "cid": row["Grootboek"]}
            for row in cost_types.fetch()
        ]
        return jsonify(results)

    def get_expenses(self, expenses_id):
        """Get expenses with expense_id"""

        expenses_info = self.ds_client.query(kind="Expenses")
        expenses_key = self.ds_client.key("Expenses", expenses_id)
        expenses_info.key_filter(expenses_key, "=")
        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = [
                {
                    "amount": ed["amount"],
                    "note": ed["note"],
                    "cost_type": ed["cost_type"],
                }
                for ed in expenses_data
            ]
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)

    def get_all_expenses(self):
        """Get JSON of all the expenses"""

        expenses_info = self.ds_client.query(kind="Expenses")
        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = [
                {
                    "amount": ed["amount"],
                    "note": ed["note"],
                    "cost_type": ed["cost_type"],
                    "date_of_claim": ed["date_of_claim"],
                    "date_of_transaction": ed["date_of_transaction"],
                    "employee": ed["employee"],
                    "status": ed["status"],
                }
                for ed in expenses_data
            ]
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)

    def add_expenses(self, data):
        """
        Add expense with given data amount and given data note. An expense can have one of 6
        statuses.
        Status Life Cycle:
        *** to_be_approved => { rejected } <= approved => payable => exported
        """
        self.get_employee_info()
        key = self.ds_client.key("Expenses")
        entity = datastore.Entity(key=key)
        date_of_claim = datetime.datetime.now()
        entity.update(
            {
                "employee": dict(
                    afas_data=self.get_employee_afas_data(
                        self.employee_info["unique_name"]
                    ),
                    email=self.employee_info["unique_name"],
                    family_name=self.employee_info["family_name"],
                    given_name=self.employee_info["given_name"],
                    full_name=self.employee_info["name"],
                ) if 'unique_name' in self.employee_info.keys() else '',
                "amount": data.amount,
                "note": data.note,
                "cost_type": data.cost_type,
                "date_of_transaction": data.date_of_transaction,
                "date_of_claim": date_of_claim.isoformat(timespec="seconds"),
                "status": dict(date_exported="never", text="to_be_approved"),
            }
        )
        self.ds_client.put(entity)
        return make_response(jsonify(entity.key.id_or_name), 201)

    @staticmethod
    def get_or_create_cloudstore_bucket(bucket_name, bucket_date):
        """Creates a new bucket."""
        storage_client = storage.Client()
        if not storage_client.bucket(config.GOOGLE_STORAGE_BUCKET).exists():
            bucket = storage_client.create_bucket(bucket_name)
            logger.info(f"Bucket {bucket} created on {bucket_date}")

    def update_exported_expenses(self, expenses_exported, document_date):
        """
        Do some sanity changed to keep data updated.
        :param expenses_exported: Expense <Entity Keys>
        :param document_date: Date when it was exported
        """
        for exp in expenses_exported:
            with self.ds_client.transaction():
                expense = self.ds_client.get(exp)
                expense["status"]["date_exported"] = document_date
                expense["status"]["text"] = "exported"
                self.ds_client.put(expense)

    def get_booking_file(self):
        """
        Create a booking file of new expenses. On export a change in the dataStore
        will run to update status.
        Exported file is stored in CloudStore with the format:
        => 13:39:00-19072019.csv
        where HH13:MM39:S00 and 19072019 the date when the export was made.
        :return:
        """
        today = datetime.datetime.now()
        no_expenses = True  # Initialise

        # Check bucket exists
        self.get_or_create_cloudstore_bucket(self.bucket_name, today)

        document_date = f"{today.day}{today:%m}{today.year}"
        document_export_date = f"{today.hour:02d}:{today.minute:02d}:{today.second:02d}-".__add__(
            document_date
        )

        never_exported = []
        expenses_query = self.ds_client.query(kind="Expenses")
        for entity in expenses_query.fetch():
            if entity["status"]["text"] in EXPORTABLE_STATUSES:
                never_exported.append(self.ds_client.key("Expenses", entity.id))

        if never_exported:
            expenses_never_exported = self.ds_client.get_multi(never_exported)

            booking_file_data = []

            for expense in expenses_never_exported:
                if expense['employee'].__len__() > 0:
                    department_number_aka_afdeling_code = expense['employee']['afas_data']['Afdeling Code']
                    company_number = self.ds_client.get(
                        self.ds_client.key('Departments', department_number_aka_afdeling_code)
                    )
                    booking_file_data.append(
                        {
                            "BoekingsomschrijvingBron":
                                f"{expense['employee']['full_name']} - {expense['date_of_transaction']}",
                            "Document-datum": document_date,
                            "Boekings-jaar": today.year,
                            "Periode": today.month,
                            "Bron-bedrijfs-nummer": 200,
                            "Bron gr boekrek": 114310,  # (voor nu, later definitief vaststellen)
                            "Bron Org Code": 94015,
                            "Bron Process": 000,
                            "Bron Produkt": 000,
                            "Bron EC": 000,
                            "Bron VP": 00,
                            "Doel-bedrijfs-nummer": company_number['Administratief Bedrijf'].split('_')[0],
                            "Doel-gr boekrek": expense["cost_type"].split(":")[1],
                            "Doel Org code": department_number_aka_afdeling_code,
                            "Doel Proces": 000,
                            "Doel Produkt": 000,
                            "Doel EC": 000,
                            "Doel VP": 00,
                            "D/C": "D",
                            "Bedrag excl. BTW": expense["amount"],
                            "BTW-Bedrag": 0.00,
                        }
                    )
                else:
                    no_expenses = False
                    return no_expenses, None, jsonify({"Info": "No Exports Available"})

            booking_file = pd.DataFrame(booking_file_data).to_csv(index=False)

            # Save File to CloudStorage
            bucket = self.cs_client.get_bucket(self.bucket_name)

            blob = bucket.blob(
                f"exports/{today.year}/{today.month}/{today.day}/{document_export_date}.csv"
            )

            blob.upload_from_string(booking_file, content_type="text/csv")
            self.update_exported_expenses(never_exported, document_export_date)

            return no_expenses, document_export_date, booking_file
        else:
            no_expenses = False
            return no_expenses, None, jsonify({"Info": "No Exports Available"})

    def get_booking_export_file(self, file_name=None, all_exports=False):
        """
        Get a booking file that has been exporteb before. If the query string param is all
        then a json file of all exports will be shown for the pre-current year
        :param file_name:
        :param all_exports:
        :return:
        """
        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)

        if all_exports:
            all_exports_files = []
            blobs = expenses_bucket.list_blobs(prefix=f"exports/{self.now.year}")

            for blob in blobs:
                blob_name = blob.name
                all_exports_files.append(
                    {"date_exported": blob_name.split("/")[4], "file_name": blob.name}
                )
            return all_exports_files
        else:
            month, day, file_name = file_name.split("_")
            with tempfile.NamedTemporaryFile(delete=False) as export_file:
                expenses_bucket.blob(
                    f"exports/{self.now.year}/{month}/{day}/{file_name}"
                ).download_to_file(export_file)
                export_file.close()
                return export_file


expense_instance = ClaimExpenses(
    expected_audience=config.OAUTH_EXPECTED_AUDIENCE,
    expected_issuer=config.OAUTH_EXPECTED_ISSUER,
    jwks_url=config.OAUTH_JWKS_URL,
)


def add_attachment():  # noqa: E501
    """Upload an attachment for your expenses

     # noqa: E501

    :param image:
    :type image: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        image = Image.from_dict(connexion.request.get_json())  # noqa: E501
    return "do some magic!"


def add_document():  # noqa: E501
    """Make new document

     # noqa: E501

    :param documents:
    :type documents: dict | bytes

    :rtype: None
    """
    if connexion.request.is_json:
        documents = Documents.from_dict(connexion.request.get_json())  # noqa: E501
    return "do some magic!"


def add_expense():
    """Make expense
    :param form_data:
    :type form_data: dict | bytes
    :rtype: None
    """
    try:
        if connexion.request.is_json:
            form_data = ExpenseData.from_dict(connexion.request.get_json())  # noqa: E501
            return expense_instance.add_expenses(form_data)
    except Exception as er:
        return {f"Error: {er}"}


def delete_attachments_by_id():  # noqa: E501
    """Delete an attachment by attachment id

     # noqa: E501


    :rtype: None
    """
    return "do some magic!"


def get_all_expenses():
    """
    Get all expenses
    :rtype: None
    """
    return expense_instance.get_all_expenses()


def get_cost_types():  # noqa: E501
    """Get all cost_types

     # noqa: E501


    :rtype: None
    """
    return expense_instance.get_cost_types()


def get_attachments_by_id():  # noqa: E501
    """Get attachment by attachment id

     # noqa: E501


    :rtype: None
    """
    return "do some magic!"


def get_document_by_id():  # noqa: E501
    """Get document by document id

     # noqa: E501


    :rtype: Documents
    """
    return "do some magic!"


def get_expenses(expenses_id):  # noqa: E501
    """Get information from expenses by id

     # noqa: E501


    :rtype: Expenses
    """
    return expense_instance.get_expenses(expenses_id)


def update_attachments_by_id():  # noqa: E501
    """Update attachment by attachment id

     # noqa: E501


    :rtype: None
    """
    return "do some magic!"


def get_booking_document_file(booking_id):
    """
    Get a requested booking file from a booking identity in the format of
    month_day_file_name => 7_12_12:34-12-07-2019
    :rtype: None
    :return"""

    export_file = expense_instance.get_booking_export_file(file_name=booking_id)
    return Response(
        open(export_file.name),
        headers={
            "Content-Type": "text/csv",
            "Content-Disposition": f"attachment; filename={booking_id}",
            "Authorization": "",
        },
    )


def get_booking_document_list():
    """
    Get a list of all documents ever created
    :rtype: None
    :return"""

    all_exports = expense_instance.get_booking_export_file(all_exports=True)
    return jsonify(all_exports)


def create_booking_document():
    """
    Make a booking file based of expenses id. Looks up all objects with
    status: exported => False. Gives the object a new status and does a few sanity checks
    """
    expenses, export_id, export_file = expense_instance.get_booking_file()

    if expenses:
        response = make_response(export_file, 200)
        response.headers = {
            "Content-Type": "text/csv",
            "Content-Disposition": f"attachment; filename={export_id}.csv",
            "Authorization": "",
            "Access-Control-Expose-Headers": 'Content-Disposition',
        }
        return response
    else:
        return export_file
