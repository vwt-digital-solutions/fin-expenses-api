import base64
import csv
import json
import secrets
import string

import datetime
import mimetypes
import tempfile
import time
import xml.etree.cElementTree as ET
import xml.dom.minidom as MD
from abc import abstractmethod
from io import BytesIO
from typing import Dict, Any

import pytz

import urllib.parse
import config
from jwkaas import JWKaas
import logging
import pandas as pd

import connexion
from flask import make_response, jsonify, Response, g
from google.cloud import datastore, storage

from openapi_server.models.booking_file import BookingFile
from openapi_server.models.cost_types import CostTypes
from openapi_server.models.documents import Documents
from openapi_server.models.status import Status
from openapi_server.models.expense_data import ExpenseData
from openapi_server.models.expense_data_array import ExpenseDataArray

logger = logging.getLogger(__name__)

# Constants
MAX_DAYS_RESOLVE = 3
EXPORTABLE_STATUSES = ["approved"]
VWT_TIME_ZONE = "Europe/Amsterdam"
FILTERED_OUT_ON_PROCESS = [
    "approved",
    "exported",
]


class ClaimExpenses:
    """
    Class based function to house all Expenses functionality

    """

    def __init__(self):
        self.ds_client = datastore.Client()  # Datastore
        self.cs_client = storage.Client()  # CloudStore
        self.employee_info = g.token
        self.bucket_name = config.GOOGLE_STORAGE_BUCKET

    def get_manager_info(self):
        """
            Create a store for OID, SUBS to anonymously identify managers

        """
        emp = self.employee_info
        key = self.ds_client.key("Manager", emp["oid"])
        if not self.ds_client.get(key):
            entity = datastore.Entity(key=key)
            entity.update({"manager_id": f"{emp['given_name']} {emp['family_name']}"})
            self.ds_client.put(entity)

    def get_employee_afas_data(self, unique_name, employee_number=None):
        """
        Data Access Link to the AFAS environment to retrieve employee information
        - Bank Account
        - Company Code
        - Any other detail we will be needing to complete the payment
        This link is made available through the HR-On boarding project
        :param employee_number: Employee number. Used when no unique name available
        :param unique_name: An email address
        """
        # Fake AFAS data for E2E:
        if unique_name == 'opensource.e2e@vwtelecom.com':
            return config.e2e_afas_data
        elif employee_number:
            employee_afas_query = self.ds_client.query(kind="AFAS_HRM")
            employee_afas_query.add_filter(
                "Personeelsnummer", "=", employee_number
            )
            result = list(employee_afas_query.fetch(limit=1))
            if result[0]:
                return dict(result[0])
            else:
                logging.warning(f"No detail of {unique_name} found in HRM -AFAS")
                return None
        else:
            employee_afas_key = self.ds_client.key("AFAS_HRM", unique_name)
            employee_afas_query = self.ds_client.get(employee_afas_key)
            if employee_afas_query:
                data = dict(employee_afas_query.items())
                return data
            else:
                logging.warning(f"No detail of {unique_name} found in HRM -AFAS")
                return None

    def create_attachment(self, attachment, expenses_id, email):
        """Creates an attachment"""

        today = pytz.UTC.localize(datetime.datetime.now())
        email_name = email.split("@")[0]
        list_object = attachment.split(".")
        for document in list_object:
            filename = f"{today.hour:02d}:{today.minute:02d}:{today.second:02d}-{today.year}{today.month}{today.day}-{list_object.index(document)}"
            bucket = self.cs_client.get_bucket(self.bucket_name)
            blob = bucket.blob(f"exports/attachments/{email_name}/{expenses_id}/{filename}")
            blob.upload_from_string(
                document.split(",")[1],
                content_type=mimetypes.guess_type(document)[0],
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

    def get_expenses(self, expenses_id, permission):
        """
        Get single expense by expense id and check if permission is employee if expense is from employee
        :param expenses_id:
        :param permission:
        :return:
        """
        with self.ds_client.transaction():
            exp_key = self.ds_client.key("Expenses", expenses_id)
            expense = self.ds_client.get(exp_key)

            if expense:
                if permission == "employee":
                    if not expense["employee"]["email"] == self.employee_info["unique_name"]:
                        return make_response(jsonify(None), 403)

                results = [
                    {
                        "amount": expense["amount"],
                        "note": expense["note"],
                        "cost_type": expense["cost_type"],
                    }
                ]
                return jsonify(results)
            else:
                return make_response(jsonify(None), 204)

    @abstractmethod
    def _check_attachment_permission(self, expense):
        pass

    def get_attachment(self, expenses_id):
        """Get attachments with expenses_id"""
        with self.ds_client.transaction():
            exp_key = self.ds_client.key("Expenses", expenses_id)
            expense = self.ds_client.get(exp_key)

        if not self._check_attachment_permission(expense):
            return make_response(jsonify(None), 403)

        email_name = expense["employee"]["email"].split("@")[0]

        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)
        blobs = expenses_bucket.list_blobs(
            prefix=f"exports/attachments/{email_name}/{str(expenses_id)}"
        )
        results = []
        for blob in blobs:
            content = blob.download_as_string()
            stream = BytesIO(content)
            stream_read = base64.b64encode(stream.read(len(content)))
            content_result = {
                "content_type": blob.content_type,
                "content": (base64.b64decode(stream_read)).decode('utf-8')
            }
            results.append(content_result)

        return jsonify(results)

    def get_all_expenses(self):
        """Get JSON of all the expenses"""

        query_filter: Dict[Any, str] = dict(
            creditor="ready_for_creditor", creditor2="approved", manager="ready_for_manager",
        )

        expenses_info = self.ds_client.query(kind="Expenses")

        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = []
            for ed in expenses_data:
                logging.info(f'get_all_expenses: [{ed}]')
                if 'status' in ed and (query_filter["creditor"] == ed["status"]["text"] or
                                       query_filter["creditor2"] == ed["status"]["text"]):
                    results.append({
                        "id": ed.id,
                        "amount": ed["amount"],
                        "note": ed["note"],
                        "cost_type": ed["cost_type"],
                        "date_of_claim": ed["date_of_claim"],
                        "date_of_transaction": ed["date_of_transaction"],
                        "employee": ed["employee"]["full_name"],
                        "status": ed["status"],
                    })
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)

    def add_expenses(self, data):
        """
        Add expense with given data amount and given data note. An expense can have one of 6
        statuses.
        Status Life Cycle:
        *** ready_for{role} => { rejected } <= approved => exported
        """
        self.get_or_create_cloudstore_bucket()
        if data.amount >= 50:
            ready_text = "ready_for_manager"
        else:
            ready_text = "ready_for_creditor"
        afas_data = self.get_employee_afas_data(
            self.employee_info["unique_name"]
        )
        logging.warning(f'add_expense: afas data found [{afas_data}]')
        if afas_data:
            key = self.ds_client.key("Expenses")
            entity = datastore.Entity(key=key, exclude_from_indexes=('employee', 'status'))
            entity.update(
                {
                    "employee": dict(
                        afas_data=afas_data,
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
                    "date_of_transaction": int(data.date_of_transaction),
                    "date_of_claim": int(time.time() * 1000),
                    "status": dict(date_exported="never", text=ready_text),
                }
            )
            self.ds_client.put(entity)
            logging.warning(f'add_expense: expense entity created [{entity}]')

            self.create_attachment(
                data.attachment,
                entity.key.id_or_name,
                self.employee_info["unique_name"]
                if "unique_name" in self.employee_info.keys()
                else "",
            )

            return make_response(jsonify(entity.key.id_or_name), 201)
        else:
            return make_response(jsonify('Employee not found'), 404)

    @abstractmethod
    def _process_status_text_update(self, item, expense):
        pass

    @abstractmethod
    def _process_status_amount_update(self, amount, expense):
        pass

    @abstractmethod
    def _prepare_context_update_expense(self, data, expense):
        pass

    def update_expenses(self, expenses_id, data):
        """
        Change the status and add note from expense
        :param expenses_id:
        :param data:
        :return:
        """
        with self.ds_client.transaction():
            exp_key = self.ds_client.key("Expenses", expenses_id)
            expense = self.ds_client.get(exp_key)
            fields, status = self._prepare_context_update_expense(data, expense)
            self._update_expenses(data, fields, status, expense)

    def _update_expenses(self, data, fields, status, expense):
        items_to_update = list(fields.intersection(set(data.keys())))
        for item in items_to_update:
            if item == "status":
                if data[item] in status:
                    self._process_status_text_update(data[item], expense)
            elif item == "rnote":
                expense["status"]["rnote"] = data[item]
            elif item == "amount":
                expense[item] = data[item]
                self._process_status_amount_update(data[item], expense)
            else:
                expense[item] = data[item]

        self.ds_client.put(expense)

    def get_or_create_cloudstore_bucket(self):
        """Creates a new bucket."""
        if not self.cs_client.bucket(config.GOOGLE_STORAGE_BUCKET).exists():
            bucket = self.cs_client.create_bucket(self.bucket_name)
            logger.info(f"Bucket {bucket} created on {datetime.datetime.now()}")

    def update_exported_expenses(self, expenses_exported, document_date, document_type):
        """
        Do some sanity changed to keep data updated.
        :param document_type: A Payment or a booking file
        :param expenses_exported: Expense <Entity Keys>
        :param document_date: Date when it was exported
        """
        status = {
            "payment_file": "exported",
            "booking_file": "exported",
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
        bic = next(r["bic"] for r in bank_data if r["identifier"] == detail[1])
        if bic:
            return bic
        else:
            return (
                "NOTPROVIDED"
            )  # ABN-AMRO will determine the BIC based on the Debtor Account

    def filter_expenses(self, document_type):
        """
        Query the expenses to return desired values
        :return:
        """
        # Check bucket exists
        self.get_or_create_cloudstore_bucket()

        now = pytz.timezone(VWT_TIME_ZONE).localize(datetime.datetime.now())
        document_date = f"{now.day}{now:%m}{now.year}"
        document_export_date = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}-".__add__(
            document_date
        )

        status = {
            "booking_file": EXPORTABLE_STATUSES,
            "payment_file": ["exported"],
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
        today = pytz.timezone(VWT_TIME_ZONE).localize(datetime.datetime.now())
        never_exported, document_export_date, document_date, document_time = self.filter_expenses(
            document_type
        )
        if never_exported:
            booking_file_data = []
            for exps in never_exported:
                expense_detail = self.ds_client.get(exps)
                if expense_detail["employee"].__len__() > 0:
                    try:
                        department_number_aka_afdeling_code = expense_detail["employee"][
                            "afas_data"
                        ]["Afdeling Code"]
                    except Exception as e:
                        department_number_aka_afdeling_code = 0000
                    company_number = self.ds_client.get(
                        self.ds_client.key(
                            "Departments", department_number_aka_afdeling_code
                        )
                    )
                    booking_file_data.append(
                        {
                            "BoekingsomschrijvingBron": f"{expense_detail['employee']['afas_data']['Personeelsnummer']}"
                                                        f" {datetime.datetime.fromtimestamp(int(expense_detail['date_of_transaction'] / 1000)).replace(tzinfo=pytz.utc).astimezone(pytz.timezone(VWT_TIME_ZONE)).strftime('%d-%m-%Y')}",
                            "Document-datum": datetime.datetime.strptime(document_date, "%d%m%Y").strftime("%d%m%Y"),
                            "Boekings-jaar": today.year,
                            "Periode": today.month,
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
                            "BTW-Bedrag": "0,00",
                        }
                    )
                else:
                    no_expenses = False
                    return (
                        no_expenses,
                        None,
                        jsonify({"Info": "No Exports Available"}),
                        None,
                    )

            booking_file = pd.DataFrame(booking_file_data).to_csv(
                sep=";", index=False, decimal=","
            )

            # Save File to CloudStorage
            bucket = self.cs_client.get_bucket(self.bucket_name)

            blob = bucket.blob(
                f"exports/{document_type}/{today.year}/{today.month}/{today.day}/{document_export_date}.csv"
            )

            blob.upload_from_string(booking_file, content_type="text/csv")
            self.update_exported_expenses(
                never_exported, document_export_date, document_type
            )
            no_expenses = True
            location = f"{today.month}_{today.day}_{document_export_date}.csv"
            return no_expenses, document_export_date, booking_file, location
        else:
            no_expenses = False
            return no_expenses, None, jsonify({"Info": "No Exports Available"}), None

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
            random_id[i: i + 3] for i in range(0, len(random_id), 3)
        ).upper()

    def create_payment_file(self, document_type, document_name):

        """
        Creates an XML file from claim expenses that have been exported. Thus a claim must have a status
        ==> status -- 'booking-file-created'
        :param document_name:
        :type document_type: object
        """
        no_expenses = True  # Initialise
        today = pytz.timezone(VWT_TIME_ZONE).localize(datetime.datetime.now())

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

            # Set namespaces
            ET.register_namespace("", "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03")
            root = ET.Element(
                "{urn:iso:std:iso:20022:tech:xsd:pain.001.001.03}Document"
            )

            root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

            customer_header = ET.SubElement(root, "CstmrCdtTrfInitn")

            # Group Header
            header = ET.SubElement(customer_header, "GrpHdr")
            ET.SubElement(header, "MsgId").text = message_id
            ET.SubElement(header, "CreDtTm").text = document_time
            ET.SubElement(header, "NbOfTxs").text = str(
                booking_file_detail.__len__()  # Number Of Transactions in the batch
            )
            initiating_party = ET.SubElement(header, "InitgPty")
            ET.SubElement(initiating_party, "Nm").text = config.VWT_ACCOUNT["bedrijf"]

            #  Payment Information
            payment_info = ET.SubElement(customer_header, "PmtInf")
            ET.SubElement(payment_info, "PmtInfId").text = message_id
            ET.SubElement(payment_info, "PmtMtd").text = "TRF"  # Standard Value
            ET.SubElement(payment_info, "NbOfTxs").text = str(
                booking_file_detail.__len__()  # Number Of Transactions in the batch
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
                # Transaction Transfer Information
                transfer = ET.SubElement(payment_info, "CdtTrfTxInf")
                transfer_payment_id = ET.SubElement(transfer, "PmtId")
                ET.SubElement(transfer_payment_id, "InstrId").text = payment_info_id
                ET.SubElement(transfer_payment_id, "EndToEndId").text = expense["data"][
                    "BoekingsomschrijvingBron"
                ]

                # Amount
                amount = ET.SubElement(transfer, "Amt")
                ET.SubElement(amount, "InstdAmt", Ccy="EUR").text = str(expense["data"][
                                                                            "Bedrag excl. BTW"
                                                                        ])
                ET.SubElement(transfer, "ChrgBr").text = "SLEV"

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
                ET.SubElement(creditor_account_id, "IBAN").text = expense[
                    "iban"
                ].replace(
                    " ", ""
                )  # <ValidationPass> on whitespaces

                # Remittance Information
                remittance_info = ET.SubElement(transfer, "RmtInf")
                ET.SubElement(remittance_info, "Ustrd").text = expense["data"][
                    "BoekingsomschrijvingBron"
                ]

            payment_file_string = ET.tostring(root, encoding="utf8", method="xml")

            # Save File to CloudStorage
            bucket = self.cs_client.get_bucket(self.bucket_name)

            blob = bucket.blob(
                f"exports/{document_type}/{today.year}/{today.month}/{today.day}/{document_name[:-4].split('_')[2]}"
            )

            # Upload file to Blob Storage
            blob.upload_from_string(payment_file_string, content_type="application/xml")

            #  Do some sanity routine

            location = f"{today.month}_{today.day}_{document_export_date}"
            payment_file = MD.parseString(payment_file_string).toprettyxml(
                encoding="utf-8"
            )

            ############################
            #  KEEP AS LAST TO HAPPEN  #
            ############################
            self.update_exported_expenses(exported, document_export_date, document_type)
            return no_expenses, document_export_date, payment_file, location
        else:
            no_expenses = False
            return (
                no_expenses,
                None,
                jsonify({"Info": "No Exports needed to create Payment Available"}),
                None,
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
        today = pytz.timezone(VWT_TIME_ZONE).localize(datetime.datetime.now())
        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)
        if all_exports:
            all_exports_files = []
            blobs = expenses_bucket.list_blobs(
                prefix=f"exports/{document_type}/{today.year}"
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
                    f"exports/booking_file/{today.year}/{month}/{day}/{file_name}"
                ).download_as_string()
                with tempfile.NamedTemporaryFile(delete=False) as file:
                    file.write(content)
                    file.close()
                    reader = pd.read_csv(file.name, sep=";").to_dict(orient="records")
                    for piece in reader:
                        employee_detail = self.get_employee_afas_data(None,
                                                                      piece["BoekingsomschrijvingBron"].split(" ")[0])
                        payment_data.append(
                            dict(data=piece, iban=employee_detail["IBAN"])
                        )
                return payment_data
            else:
                with tempfile.NamedTemporaryFile(delete=False) as export_file:
                    expenses_bucket.blob(
                        f"exports/{document_type}/{today.year}/{month}/{day}/{file_name}"
                    ).download_to_file(export_file)
                    export_file.close()
                    return export_file

    def _create_expenses_query(self):
        return self.ds_client.query(kind="Expenses")

    @staticmethod
    def _process_expenses_info(expenses_info):
        expenses_data = expenses_info.fetch()
        if expenses_data:
            return jsonify([
                {
                    "id": ed.id,
                    "amount": ed["amount"],
                    "note": ed["note"],
                    "cost_type": ed["cost_type"],
                    "date_of_claim": ed["date_of_claim"],
                    "date_of_transaction": ed["date_of_transaction"],
                    "employee": ed["employee"]["full_name"],
                    "status": ed["status"],
                }
                for ed in expenses_data
            ])
        else:
            return make_response(jsonify(None), 204)


class EmployeeExpenses(ClaimExpenses):
    def _check_attachment_permission(self, expense):
        if expense["employee"]["email"] != self.employee_info["unique_name"]:
            return False
        else:
            return True

    def __init__(self, employee_id):
        super().__init__()
        self.employee_id = employee_id

    def get_all_expenses(self):
        expenses_info = self._create_expenses_query()
        expenses_info.add_filter(
            "employee.afas_data.email_address", "=", self.employee_info["unique_name"]
        )
        return self._process_expenses_info(expenses_info)

    def _prepare_context_update_expense(self, data, expense):
        # Check if expense is from employee
        if not expense["employee"]["email"] == self.employee_info["unique_name"]:
            return make_response(jsonify(None), 403)
        # Check if status is either rejected_by_manager or rejected_by_creditor
        if expense["status"]["text"] != "rejected_by_manager" and expense["status"]["text"] != "rejected_by_creditor":
            return make_response(jsonify(None), 403)

        fields = {
            "status",
            "amount",
            "date_of_transaction",
            "cost_type",
            "note"
        }

        status = {
            "ready_for_manager",
            "ready_for_creditor",
            "cancelled",
        }
        return fields, status

    def _process_status_text_update(self, item, expense):
        pass

    def _process_status_amount_update(self, amount, expense):
        # If amount is set when employee updates expense check what status it should be
        # If amount is less then 50 manager can be skipped
        if amount < 50:
            expense["status"]["text"] = "ready_for_creditor"
        else:
            expense["status"]["text"] = "ready_for_manager"


class DepartmentExpenses(ClaimExpenses):
    def _check_attachment_permission(self, expense):
        return True

    def __init__(self, department_id):
        super().__init__()
        self.department_id = department_id

    def get_all_expenses(self):
        expenses_info = self._create_expenses_query()
        # self.get_manager_info()
        # manager = self.ds_client.get(self.ds_client.key("Manager", self.department_id))
        # query_filter: Dict[Any, str] = dict(
        #     creditor="ready_for_creditor", creditor2="approved", manager="ready_for_manager",
        # )
        expenses_info.add_filter(
            "status.text",
            "=",
            "ready_for_manager"
        )
        manager_name = self.employee_info['name']
        manager_name = (manager_name.split(',')[1] + ' ' + manager_name.split(',')[0]).strip()
        expenses_info.add_filter(
            "employee.afas_data.Manager",
            "=",
            manager_name
        )
        # expenses_data = expenses_info.fetch(limit=10)
        return self._process_expenses_info(expenses_info)

    def _prepare_context_update_expense(self, data, expense):
        fields = {
            "status",
            "amount",
            "date_of_transaction",
            "cost_type",
            "rnote"
        }
        status = {
            "ready_for_creditor",
            "rejected_by_manager",
        }
        return fields, status

    def _process_status_text_update(self, item, expense):
        expense["status"]["text"] = item

    def _process_status_amount_update(self, amount, expense):
        pass


class ControllerExpenses(ClaimExpenses):
    def _check_attachment_permission(self, expense):
        return True

    def __init__(self):
        super().__init__()

    def get_all_expenses(self):
        expenses_info = self._create_expenses_query()
        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = [
                {
                    "id": ed.id,
                    "amount": ed["amount"],
                    "note": ed["note"],
                    "cost_type": ed["cost_type"],
                    "date_of_claim": datetime.datetime.fromtimestamp(int(ed["date_of_claim"] / 1000)).replace(
                        tzinfo=pytz.utc).astimezone(pytz.timezone(VWT_TIME_ZONE)).strftime('%d-%m-%Y %H:%M:%S'),
                    "date_of_transaction": datetime.datetime.fromtimestamp(int(ed["date_of_transaction"] / 1000)
                                                                           ).replace(tzinfo=pytz.utc).astimezone
                    (pytz.timezone(VWT_TIME_ZONE)).strftime('%d %b %Y'),
                    "employee": ed["employee"]["full_name"],
                    "status": ed["status"],
                }
                for ed in expenses_data
            ]
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)
        pass

    def _prepare_context_update_expense(self, data, expense):
        fields = {
            "status",
            "amount",
            "date_of_transaction",
            "cost_type",
            "rnote"
        }
        status = {
            "rejected_by_creditor",
            "approved",
        }
        return fields, status

    def _process_status_text_update(self, item, expense):
        expense["status"]["text"] = item

    def _process_status_amount_update(self, amount, expense):
        pass


def add_expense():
    """Make expense
    :param form_data:
    :type form_data: dict | bytes
    :rtype: None
    """
    try:
        if connexion.request.is_json:
            expense_instance = ClaimExpenses()
            form_data = ExpenseData.from_dict(
                connexion.request.get_json()
            )  # noqa: E501
            return expense_instance.add_expenses(form_data)
    except Exception as er:
        logging.exception('Exception on add_expense')
        return jsonify(er.args), 500


def get_all_expenses():
    """
    Get all expenses
    :rtype: None
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_all_expenses()


def get_cost_types():  # noqa: E501
    """Get all cost_type
    :rtype: None
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_cost_types()


def get_document(document_date, document_type):
    """
    Get a requested booking or payment file from a booking or payment identity in the format of
    1. Booking File => month_day_file_name => 7_12_12:34-12-07-2019
    2. Document File => month_day_file_name => 7_12_12:34-12-07-2019
    e.g => http://{HOST}/finances/expenses/documents/7_12_12:34-12-07-2019/kinds/payment_file
    :rtype: None
    :return"""

    expense_instance = ClaimExpenses()
    export_file = expense_instance.get_document_files_or_list(
        document_id=document_date, document_type=document_type
    )
    # Separate Content
    content_response = {
        "payment_file": {
            "content_type": "application/xml",
            "file": MD.parse(export_file.name).toprettyxml(encoding="utf-8").decode()
            if document_type == "payment_file"
            else "",
        },
        "booking_file": {
            "content_type": "text/csv",
            "file": open(export_file.name, "r")
            if document_type == "booking_file"
            else "",
        },
    }

    mime_type = content_response[document_type]
    return Response(
        content_response[document_type]["file"],
        headers={
            "Content-Type": f"{mime_type['content_type']}",
            "Content-Disposition": f"attachment; filename={document_date}.{mime_type['content_type'].split('/')[1]}",
            "Authorization": "",
        },
    )


def get_document_list(document_type):
    """
    Get a list of all documents ever created
    :rtype: None
    :return"""

    expense_instance = ClaimExpenses()
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

    expense_instance = ClaimExpenses()
    expenses, export_id, export_file, location = (
        expense_instance.create_booking_file(document_type)
        if document_type == "booking_file"
        else expense_instance.create_payment_file(document_type, document_name)
    )

    # Separate Content
    content_type = {"payment_file": "application/xml", "booking_file": "text/csv"}

    if expenses:
        mime_type = content_type[document_type]
        response = make_response(export_file, 200)
        response.headers = {
            "Content-Type": f"{mime_type}",
            "Content-Disposition":
                f"attachment; filename={export_id}.{mime_type.split('/')[1]}; file_location={location}",
            "Authorization": "",
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
        return response
    else:
        return export_file


def get_department_expenses(department_id):
    """
    Get expenses corresponding to this manager
    :param department_id:
    """
    expense_instance = DepartmentExpenses(department_id)
    return expense_instance.get_all_expenses()


def get_controller_expenses():
    """
    Get all expenses for controller
    :return:
    """
    expense_instance = ControllerExpenses()
    return expense_instance.get_all_expenses()


def get_employee_expenses(employee_id):
    """
    Get expenses corresponding to the logged in employee
    :param employee_id:
    """
    expense_instance = EmployeeExpenses(employee_id)
    return expense_instance.get_all_expenses()


def update_expenses_finance(expenses_id):
    """
    Update expense by expense_id with creditor permissions
    :rtype: Expenses
    """
    try:
        if connexion.request.is_json:
            form_data = json.loads(connexion.request.get_data().decode())
            expense_instance = ControllerExpenses()
            return expense_instance.update_expenses(expenses_id, form_data)
    except Exception as er:
        return jsonify(er.args), 500


def update_expenses_employee(expenses_id):
    """
    Update expense by expense_id with employee permissions
    :param expenses_id:
    :return:
    """
    try:
        if connexion.request.is_json:
            form_data = json.loads(connexion.request.get_data().decode())
            expense_instance = EmployeeExpenses(None)
            return expense_instance.update_expenses(expenses_id, form_data)
    except Exception as er:
        return jsonify(er.args), 500


def update_expenses_manager(expenses_id):
    """
    Update expense by expense_id with employee permissions
    :param expenses_id:
    :return:
    """
    try:
        if connexion.request.is_json:
            form_data = json.loads(connexion.request.get_data().decode())
            expense_instance = DepartmentExpenses(None)
            return expense_instance.update_expenses(expenses_id, form_data)
    except Exception as er:
        return jsonify(er.args), 500


def get_expenses_employee(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_expenses(expenses_id, "employee")


def get_expenses_finances(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_expenses(expenses_id, "creditor")


def get_attachment_finances_manager(expenses_id):
    """
    Get attachment by expenses id
    :param expenses_id:
    :return:
    """
    expense_instance = DepartmentExpenses(None)
    return expense_instance.get_attachment(expenses_id)


def get_attachment_finances_creditor(expenses_id):
    """
    Get attachment by expenses id
    :param expenses_id:
    :return:
    """
    expense_instance = ControllerExpenses()
    return expense_instance.get_attachment(expenses_id)


def get_attachment_employee(expenses_id):
    """
    Get attachment by expenses id
    :param expenses_id:
    :return:
    """
    expense_instance = EmployeeExpenses(None)
    return expense_instance.get_attachment(expenses_id)
