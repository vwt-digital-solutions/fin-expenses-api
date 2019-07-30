import base64
import csv
import secrets
import string

import datetime
import mimetypes
import tempfile
import xml.etree.cElementTree as ET

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
EXPORTABLE_STATUSES = ["payable", "approved", "late_on_approval", ""]


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

    def create_attachment(self, attachment, expenses_id, email):
        """Creates an attachment"""

        today = self.now
        email_name = email.split("@")[0]

        filename = f"{today.hour:02d}:{today.minute:02d}:{today.second:02d}-{today.year}{today.month}{today.day}"

        bucket = self.cs_client.get_bucket(self.bucket_name)
        blob = bucket.blob(f"exports/attachments/{email_name}/{expenses_id}/{filename}")
        blob.upload_from_string(
            base64.b64decode(attachment.split(",")[1]),
            content_type=mimetypes.guess_type(attachment)[0],
        )

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
                )
                if "unique_name" in self.employee_info.keys()
                else "",
                "amount": data.amount,
                "note": data.note,
                "cost_type": data.cost_type,
                "date_of_transaction": data.date_of_transaction,
                "date_of_claim": date_of_claim.isoformat(timespec="seconds"),
                "status": dict(date_exported="never", text="to_be_approved"),
            }
        )
        self.ds_client.put(entity)

        self.create_attachment(
            data.attachment, entity.key.id_or_name, self.employee_info["unique_name"]
        )

        return make_response(jsonify(entity.key.id_or_name), 201)

    @staticmethod
    def get_or_create_cloudstore_bucket(bucket_name, bucket_date):
        """Creates a new bucket."""
        storage_client = storage.Client()
        if not storage_client.bucket(config.GOOGLE_STORAGE_BUCKET).exists():
            bucket = storage_client.create_bucket(bucket_name)
            logger.info(f"Bucket {bucket} created on {bucket_date}")

    def update_exported_expenses(self, expenses_exported, document_date, document_type):
        """
        Do some sanity changed to keep data updated.
        :param document_type: A Payment or a booking file
        :param expenses_exported: Expense <Entity Keys>
        :param document_date: Date when it was exported
        """
        status = {
            "payment_file": "payment-document-created",
            "booking_file": "booking-file-created",
        }

        for exp in expenses_exported:
            with self.ds_client.transaction():
                expense = self.ds_client.get(exp)
                expense["status"]["date_exported"] = document_date
                expense["status"]["text"] = status[document_type]
                self.ds_client.put(expense)

    @staticmethod
    def get_iban_details(iban):
        """
        Get the needed IBAN numbers of any dutch rekening number
        :param iban:
        :return:
        """
        detail = iban.split(" ")
        bank_data = config.BIC_NUMBERS
        return next(r["bic"] for r in bank_data if r["identifier"] == detail[1])

    def filter_expenses(self, document_type):
        """
        Query the expenses to return desired values
        :return:
        """
        # Check bucket exists
        self.get_or_create_cloudstore_bucket(self.bucket_name, self.now)

        now = self.now
        document_date = f"{now.day}{now:%m}{now.year}"
        document_export_date = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}-".__add__(
            document_date
        )

        status = {
            "booking_file": EXPORTABLE_STATUSES,
            "payment_file": ["booking-file-created"],
        }

        never_exported = []
        expenses_query = self.ds_client.query(kind="Expenses")
        for entity in expenses_query.fetch():
            if entity["status"]["text"] in status[document_type]:
                never_exported.append(self.ds_client.key("Expenses", entity.id))
        return (
            never_exported,
            document_export_date,
            document_date,
            now.isoformat(timespec="seconds"),
        )

    def create_booking_file(self, document_type):
        """
        Create a booking file
        :param document_type:
        :return:
        """
        never_exported, document_export_date, document_date, document_time = self.filter_expenses(
            document_type
        )
        if never_exported:
            booking_file_data = []
            for exps in never_exported:
                expense_detail = self.ds_client.get(exps)
                if expense_detail["employee"].__len__() > 0:
                    department_number_aka_afdeling_code = expense_detail["employee"][
                        "afas_data"
                    ]["Afdeling Code"]
                    company_number = self.ds_client.get(
                        self.ds_client.key(
                            "Departments", department_number_aka_afdeling_code
                        )
                    )
                    booking_file_data.append(
                        {
                            "BoekingsomschrijvingBron": f"{expense_detail['employee']['email'].split('@')[0]} - {expense_detail['employee']['family_name']}"
                            f" - {expense_detail['date_of_transaction']}",
                            "Document-datum": document_date,
                            "Boekings-jaar": self.now.year,
                            "Periode": self.now.month,
                            "Bron-bedrijfs-nummer": 200,
                            "Bron gr boekrek": 114310,  # (voor nu, later definitief vaststellen)
                            "Bron Org Code": 94015,
                            "Bron Process": "000",
                            "Bron Produkt": "000",
                            "Bron EC": "000",
                            "Bron VP": "00",
                            "Doel-bedrijfs-nummer": company_number[
                                "Administratief Bedrijf"
                            ].split("_")[0],
                            "Doel-gr boekrek": expense_detail["cost_type"].split(":")[
                                1
                            ],
                            "Doel Org code": department_number_aka_afdeling_code,
                            "Doel Proces": "000",
                            "Doel Produkt": "000",
                            "Doel EC": "000",
                            "Doel VP": "00",
                            "D/C": "C",
                            "Bedrag excl. BTW": expense_detail["amount"],
                            "BTW-Bedrag": "0.00",
                        }
                    )
                else:
                    no_expenses = False
                    return no_expenses, None, jsonify({"Info": "No Exports Available"})

            booking_file = pd.DataFrame(booking_file_data).to_csv(index=False)

            # Save File to CloudStorage
            bucket = self.cs_client.get_bucket(self.bucket_name)

            blob = bucket.blob(
                f"exports/{document_type}/{self.now.year}/{self.now.month}/{self.now.day}/{document_export_date}.csv"
            )

            blob.upload_from_string(booking_file, content_type="text/csv")
            self.update_exported_expenses(
                never_exported, document_export_date, document_type
            )
            no_expenses = True
            return no_expenses, document_export_date, booking_file
        else:
            no_expenses = False
            return no_expenses, None, jsonify({"Info": "No Exports Available"})

    @staticmethod
    def generate_random_msgid():
        """
        A message ID that will be read in the XML should be unique. This has
        a minimal random collision disadvantage
        :return:
        """
        alphabet = string.ascii_letters + string.digits
        while True:
            random_id = "".join(secrets.choice(alphabet) for i in range(9))
            if (
                any(c.islower() for c in random_id)
                and any(c.isupper() for c in random_id)
                and sum(c.isdigit() for c in random_id) >= 3
            ):
                break
        return "/".join(
            random_id[i : i + 3] for i in range(0, len(random_id), 3)
        ).upper()

    def create_payment_file(self, document_type, document_name):

        """
        Creates an XML file from claim expenses that have been exported. Thus a claim must have a status
        ==> status -- 'booking-file-created'
        :param document_name:
        :type document_type: object
        """
        no_expenses = True  # Initialise
        exported, document_export_date, document_date, document_time = self.filter_expenses(
            document_type
        )
        str_num_unique = string.ascii_letters[:8] + string.digits
        if exported:
            booking_file_detail = self.get_document_files_or_list(
                document_type=document_type, document_id=document_name, raw=True
            )
            message_id = f"{200}/{self.generate_random_msgid()}"
            payment_info_id = (
                f"{200}/{''.join(secrets.choice(str_num_unique.upper()) for i in range(3))}/"
                f"{''.join(secrets.choice(string.digits) for i in range(8))}"
            )
            ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
            root = ET.Element("Document")
            customer_header = ET.SubElement(root, "CstmrCdtTrfInitn")

            # Group Header
            header = ET.SubElement(customer_header, "GrpHdr")
            ET.SubElement(header, "MsgId").text = message_id
            ET.SubElement(header, "CreDtTm").text = document_time
            ET.SubElement(header, "NbOfTxs").text = "45"  # Default Value
            initiating_party = ET.SubElement(header, "InitgPty")
            ET.SubElement(initiating_party, "Nm").text = config.VWT_ACCOUNT["bedrijf"]

            #  Payment Information
            payment_info = ET.SubElement(customer_header, "PmtInf")
            ET.SubElement(payment_info, "PmtInfId").text = payment_info_id
            ET.SubElement(payment_info, "PmtMtd").text = "TRF"  # Standard Value
            ET.SubElement(payment_info, "NbOfTxs").text = str(
                booking_file_detail.__len__()
            )

            # Payment Type Information
            payment_typ_info = ET.SubElement(payment_info, "PmtTpInf")
            ET.SubElement(payment_typ_info, "InstrPrty").text = "NORM"
            payment_tp_service_level = ET.SubElement(payment_typ_info, "SvcLvl")
            ET.SubElement(payment_tp_service_level, "Cd").text = "SEPA"

            ET.SubElement(payment_info, "ReqdExctnDt").text = document_time.split("T")[
                0
            ]

            # Debitor Information
            payment_debitor_info = ET.SubElement(payment_info, "Dbtr")
            ET.SubElement(payment_debitor_info, "Nm").text = "VWT BV"
            payment_debitor_account = ET.SubElement(payment_info, "DbtrAcct")
            payment_debitor_account_id = ET.SubElement(payment_debitor_account, "Id")
            ET.SubElement(payment_debitor_account_id, "IBAN").text = config.VWT_ACCOUNT[
                "iban"
            ]

            # Debitor Agent Tags Information
            payment_debitor_agent = ET.SubElement(payment_info, "DbtrAgt")
            payment_debitor_agent_id = ET.SubElement(
                payment_debitor_agent, "FinInstnId"
            )
            ET.SubElement(payment_debitor_agent_id, "BIC").text = config.VWT_ACCOUNT[
                "bic"
            ]

            for expense in booking_file_detail:
                # Transaction Transfer Test Information
                transfer = ET.SubElement(payment_info, "CdtTrfTxInf")
                transfer_payment_id = ET.SubElement(transfer, "PmtId")
                ET.SubElement(transfer_payment_id, "InstrId").text = payment_info_id
                ET.SubElement(transfer_payment_id, "EndToEndId").text = expense["data"][
                    "BoekingsomschrijvingBron"
                ]

                # Amount
                amount = ET.SubElement(transfer, "Amt")
                ET.SubElement(amount, "InstdAmt", Ccy="EUR").text = expense["data"][
                    "Bedrag excl. BTW"
                ]
                ET.SubElement(amount, "ChrgBr").text = "SLEV"

                # Creditor Agent Tag Information
                amount_agent = ET.SubElement(transfer, "CdtrAgt")
                payment_creditor_agent_id = ET.SubElement(amount_agent, "FinInstnId")
                ET.SubElement(
                    payment_creditor_agent_id, "BIC"
                ).text = self.get_iban_details(expense["iban"])

                # Creditor name
                creditor_name = ET.SubElement(transfer, "Cdtr")
                ET.SubElement(creditor_name, "Nm").text = expense["data"][
                    "BoekingsomschrijvingBron"
                ].split("-")[1]

                # Creditor Account
                creditor_account = ET.SubElement(transfer, "CdtrAcct")
                creditor_account_id = ET.SubElement(creditor_account, "Id")
                ET.SubElement(creditor_account_id, "IBAN").text = expense["iban"]

                # Remittance Information
                remittance_info = ET.SubElement(transfer, "RmtInf")
                ET.SubElement(remittance_info, "Ustrd").text = expense["data"][
                    "BoekingsomschrijvingBron"
                ]

            payment_file_string = ET.tostring(root, encoding="utf8", method="xml")

            # Save File to CloudStorage
            bucket = self.cs_client.get_bucket(self.bucket_name)

            blob = bucket.blob(
                f"exports/{document_type}/{self.now.year}/{self.now.month}/{self.now.day}/{document_export_date}"
            )

            # Upload file to Blob Storage
            blob.upload_from_string(payment_file_string, content_type="application/xml")

            with tempfile.NamedTemporaryFile(delete=False) as file:
                ET.ElementTree(root).write(
                    open(f"{file.name}.xml", "wb"),
                    encoding="utf-8",
                    xml_declaration=True,
                    method="xml",
                )
                file.close()

                ready_payment_file = open(f"{file.name}.xml", "r")

                #  Do some sanity routine
                self.update_exported_expenses(
                    exported, document_export_date, document_type
                )
                return no_expenses, document_export_date, ready_payment_file.read()
        else:
            no_expenses = False
            return (
                no_expenses,
                None,
                jsonify({"Info": "No Exports needed to create Payment Available"}),
            )

    def get_document_files_or_list(
        self, document_type, document_id=None, all_exports=False, raw=None
    ):
        """
        1 => Gets a booking file or a list of them that has been exported before. If the query string param is all
        then a json file of all exports will be shown for the pre-current year

        2 => Gets a payment file or a list of them  that has been exported created. Just like the booking file these are
        based on once exported claim expenses
        A claim status MUST have => 'exported'
        :param raw: If calling a file to be made into a payment file
        :param document_type:
        :param document_id:
        :param all_exports:
        :return:
        """
        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)
        if all_exports:
            all_exports_files = []
            blobs = expenses_bucket.list_blobs(
                prefix=f"exports/{document_type}/{self.now.year}"
            )

            for blob in blobs:
                blob_name = blob.name
                all_exports_files.append(
                    {"date_exported": blob_name.split("/")[5], "file_name": blob.name}
                )
            return all_exports_files
        else:
            month, day, file_name = document_id.split("_")
            if raw:
                ###########################################################################
                # Raw is being called by the payment file creation to reuse this logic to #
                # collect all data needed to create a payment file from the booking file  #
                ###########################################################################
                payment_data = []
                content = expenses_bucket.blob(
                    f"exports/booking_file/{self.now.year}/{month}/{day}/{file_name}"
                ).download_as_string()
                with tempfile.NamedTemporaryFile(delete=False) as file:
                    file.write(content)
                    file.close()
                    opened_content = open(file.name, "r")
                    reader = csv.DictReader(opened_content)
                    for piece in reader:
                        employee_detail = self.get_employee_afas_data(
                            piece["BoekingsomschrijvingBron"].split("-")[0].strip()
                        )
                        payment_data.append(
                            dict(data=piece, iban=employee_detail["IBAN"])
                        )
                return payment_data
            else:
                with tempfile.NamedTemporaryFile(delete=False) as export_file:
                    expenses_bucket.blob(
                        f"exports/{document_type}/{self.now.year}/{month}/{day}/{file_name}"
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
            form_data = ExpenseData.from_dict(
                connexion.request.get_json()
            )  # noqa: E501
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


def get_expenses(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    return expense_instance.get_expenses(expenses_id)


def update_attachments_by_id():
    """Update attachment by attachment id"""
    return "do some magic!"


def get_document(document_date, document_type):
    """
    Get a requested booking or payment file from a booking or payment identity in the format of
    1. Booking File => month_day_file_name => 7_12_12:34-12-07-2019
    2. Document File => month_day_file_name => 7_12_12:34-12-07-2019
    e.g => http://{HOST}/finances/expenses/documents/7_12_12:34-12-07-2019/kinds/payment_file
    :rtype: None
    :return"""

    export_file = expense_instance.get_document_files_or_list(
        document_id=document_date, document_type=document_type
    )
    # Separate Content
    content_type = {"payment_file": "application/xml", "booking_file": "text/csv"}
    return Response(
        open(export_file.name),
        headers={
            "Content-Type": f"{content_type[document_type]}",
            "Content-Disposition": f"attachment; filename={document_date}.{content_type[document_type].split('/')[1]}",
            "Authorization": "",
        },
    )


def get_document_list(document_type):
    """
    Get a list of all documents ever created
    :rtype: None
    :return"""

    all_exports = expense_instance.get_document_files_or_list(
        all_exports=True, document_type=document_type
    )
    return jsonify(all_exports)


def create_document(document_type):
    """
    Make a booking file based of expenses id. Looks up all objects with
    status: exported => False. Gives the object a new status and does a few sanity checks
    """
    document_name = connexion.request.args.get("name")

    expenses, export_id, export_file = (
        expense_instance.create_booking_file(document_type)
        if document_type == "booking_file"
        else expense_instance.create_payment_file(document_type, document_name)
    )

    # Separate Content
    content_type = {"payment_file": "application/xml", "booking_file": "text/csv"}

    if expenses:
        response = make_response(export_file, 200)
        response.headers = {
            "Content-Type": f"{content_type[document_type]}",
            "Content-Disposition": f"attachment; filename={export_id}.{content_type[document_type].split('/')[1]}",
            "Authorization": "",
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        return response
    else:
        return export_file
