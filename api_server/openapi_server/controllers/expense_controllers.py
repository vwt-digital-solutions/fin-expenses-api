import base64
import copy
import json
import os
import requests
import re
import csv

import datetime
import tempfile
import xml.etree.cElementTree as ET
import defusedxml.minidom as MD
from abc import abstractmethod
from io import BytesIO
from typing import Dict, Any
import dateutil

import pytz
import config
import logging
import pandas as pd
from PyPDF2 import PdfFileReader, PdfFileWriter

import connexion
import googleapiclient.discovery
from flask import make_response, jsonify, Response, g, request, send_file
from google.cloud import datastore, storage, kms_v1
from google.oauth2 import service_account
from apiclient import errors
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from openapi_server.models.attachment_data import AttachmentData
from openapi_server.models.expense_data import ExpenseData
from openapi_server.controllers.businessrules_controller import BusinessRulesEngine

from OpenSSL import crypto

logger = logging.getLogger(__name__)

# Constants
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
        # Decrypt Gmail SDK credentials & init G Mail service
        delegated_credentials = service_account.Credentials.from_service_account_info(
            json.loads(self.decrypt_gmailsdk_credentials()),
            scopes=['https://www.googleapis.com/auth/gmail.send'],
            subject=config.GMAIL_SUBJECT_ADDRESS)

        self.gmail_service = googleapiclient.discovery.build(
            'gmail', 'v1', credentials=delegated_credentials,
            cache_discovery=False)

        self.ds_client = datastore.Client()  # Datastore
        self.cs_client = storage.Client()  # CloudStores
        self.employee_info = g.token
        self.bucket_name = config.GOOGLE_STORAGE_BUCKET

    def decrypt_gmailsdk_credentials(self):
        file_name = 'gmailsdk_credentials'
        kms_client = kms_v1.KeyManagementServiceClient()
        pk_passphrase = kms_client.crypto_key_path_path(
            os.environ['GOOGLE_CLOUD_PROJECT'], 'europe-west1',
            os.environ['GOOGLE_CLOUD_PROJECT'] + '-keyring',
            config.GMAIL_CREDENTIALS_KEY)
        decrypt_response = kms_client.decrypt(
            pk_passphrase, open(f"{file_name}.enc", "rb").read())

        return decrypt_response.plaintext.decode("utf-8").replace('\n', '')

    def get_employee_afas_data(self, unique_name):
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

        employee_afas_key = self.ds_client.key("AFAS_HRM", unique_name)
        employee_afas_query = self.ds_client.get(employee_afas_key)
        if employee_afas_query:
            data = dict(employee_afas_query.items())
            return data

        logging.warning(f"No detail of {unique_name} found in HRM -AFAS")
        return None

    def create_attachment(self, attachment, expenses_id, email):
        """Creates an attachment"""
        today = pytz.UTC.localize(datetime.datetime.now())
        email_name = email.split("@")[0]
        filename = f"{today.hour:02d}:{today.minute:02d}:{today.second:02d}-{today.year}{today.month}{today.day}" \
                   f"-{attachment.name}"
        bucket = self.cs_client.get_bucket(self.bucket_name)
        blob = bucket.blob(f"exports/attachments/{email_name}/{expenses_id}/{filename}")

        try:
            if ',' not in attachment.content:
                return False
            content_type = re.search(r"(?<=^data:)(.*)(?=;base64)", attachment.content.split(",")[0])
            content = base64.b64decode(attachment.content.split(",")[1])  # Set the content from base64
            if not content_type or not content:
                return False
            content_type = content_type.group()
            if content_type == 'application/pdf':
                writer = PdfFileWriter()  # Create a PdfFileWriter to store the new PDF
                with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                    temp_file.write(content)
                    temp_file.close()
                    reader = PdfFileReader(open(temp_file.name, 'rb'))  # Read the bytes from temp with original b64
                    [writer.addPage(reader.getPage(i)) for i in range(0, reader.getNumPages())]  # Add pages
                    writer.removeLinks()  # Remove all linking in PDF (not external website links)
                    with tempfile.NamedTemporaryFile(mode='w+b', delete=False) as temp_flat_file:
                        writer.write(temp_flat_file)  # Let the writer write into the temp file
                        temp_flat_file.close()  # Close the temp file (stays in `with`)
                        content = open(temp_flat_file.name, 'rb').read()  # Read the content from the temp file

            blob.upload_from_string(
                content,  # Upload content (can be decoded b64 from request or read data from temp flat file
                content_type=content_type
            )
            return True
        except Exception:
            logging.exception("Something went wrong with the attachment upload")
            return False

    def delete_attachment(self, expenses_id, attachments_name):
        """
        Deletes attachment based on expense id and attachment name
        :param expenses_id:
        :param attachments_name:
        """
        email_name = self.employee_info["unique_name"].split("@")[0]

        exp_key = self.ds_client.key("Expenses", expenses_id)
        expense = self.ds_client.get(exp_key)

        if expense["employee"]["email"] != self.employee_info["unique_name"]:
            return make_response(jsonify('No match on email'), 403)

        bucket = self.cs_client.get_bucket(self.bucket_name)
        blob = bucket.blob(f"exports/attachments/{email_name}/{expenses_id}/{attachments_name}")

        blob.delete()

        return '', 204

    def get_cost_types(self):
        """
        Get cost types from a CSV file
        :return:
        """

        cost_types = self.ds_client.query(kind="CostTypes")
        results = [
            {
                "ctype": row.get("Omschrijving", ""),
                "cid": row.get("Grootboek", ""),
                "managertype": row.get("ManagerType", "linemanager"),
                "message": row.get("Message", {})
            }
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
                        return make_response(jsonify('No match on email'), 403)

                results = [
                    {
                        "amount": expense["amount"],
                        "note": expense["note"],
                        "cost_type": expense["cost_type"],
                    }
                ]
                return jsonify(results)

            return make_response(jsonify(None), 204)

    @abstractmethod
    def _check_attachment_permission(self, expense):
        pass

    def get_attachment(self, expenses_id):
        """Get attachments with expenses_id"""
        with self.ds_client.transaction():
            exp_key = self.ds_client.key("Expenses", expenses_id)
            expense = self.ds_client.get(exp_key)

        if not expense:
            return make_response(jsonify('Expense not found'), 404)
        if not self._check_attachment_permission(expense):
            return make_response(jsonify('Unauthorized'), 403)

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
                "content": stream_read.decode('utf-8'),
                "name": blob.name.split('/')[-1]
            }
            results.append(content_result)

        return jsonify(results)

    @abstractmethod
    def get_all_expenses(self):
        pass

    def add_expenses(self, data):
        """
        Add expense with given data amount and given data note. An expense can have one of 6
        statuses.
        Status Life Cycle:
        *** ready_for{role} => { rejected } <= approved => exported
        """
        if "unique_name" in self.employee_info.keys():
            ready_text = "draft"

            afas_data = self.get_employee_afas_data(self.employee_info["unique_name"])
            if afas_data:
                try:
                    BusinessRulesEngine().process_rules(data, afas_data)
                    data.manager_type = self._process_expense_manager_type(
                        data.cost_type)
                except ValueError as exception:
                    return make_response(jsonify(str(exception)), 400)
                else:
                    key = self.ds_client.key("Expenses")
                    entity = datastore.Entity(key=key)
                    new_expense = {
                        "employee": dict(
                            afas_data=afas_data,
                            email=self.employee_info["unique_name"],
                            family_name=self.employee_info["family_name"],
                            given_name=self.employee_info["given_name"],
                            full_name=self.employee_info["name"],
                        ),
                        "amount": data.amount,
                        "note": data.note,
                        "cost_type": data.cost_type,
                        "transaction_date": data.transaction_date,
                        "claim_date": datetime.datetime.utcnow().isoformat(timespec="seconds") + 'Z',
                        "status": dict(export_date="never", text=ready_text),
                        "manager_type": data.manager_type
                    }

                    entity.update(new_expense)
                    self.ds_client.put(entity)
                    self.expense_journal({}, entity)

                    if ready_text == 'ready_for_manager':
                        self.send_email_notification(
                            'add_expense', afas_data,
                            entity.key.id_or_name)

                    return make_response(
                        jsonify(entity.key.id_or_name), 201)
            else:
                return make_response(jsonify('Employee not found'), 403)
        else:
            return make_response(jsonify('Employee not unique'), 403)

    def _process_status_text_update(self, item, expense):
        if expense['status']['text'] in ['rejected_by_creditor',
                                         'rejected_by_manager'] \
                and item == 'ready_for_manager':
            expense["status"]["text"] = self._determine_status_amount_update(
                expense['amount'], expense['cost_type'], item)
        else:
            expense["status"]["text"] = item

    def _determine_status_amount_update(self, amount, cost_type, item):
        min_amount = self._process_expense_min_amount(cost_type)
        manager_type = self._process_expense_manager_type(cost_type)

        return "ready_for_creditor" if \
            min_amount > 0 and amount < min_amount and \
            manager_type != 'leasecoordinator' else item

    @abstractmethod
    def _prepare_context_update_expense(self, expense):
        pass

    def update_expenses(self, expenses_id, data, note_check=False):
        """
        Change the status and add note from expense
        :param expenses_id:
        :param data:
        :param note_check:
        :return:
        """
        if not data.get('rnote') and note_check and (data['status'] == 'rejected_by_manager'
                                                     or data['status'] == 'rejected_by_creditor'):
            return jsonify('Some data is missing'), 400

        with self.ds_client.transaction():
            exp_key = self.ds_client.key("Expenses", expenses_id)
            expense = self.ds_client.get(exp_key)
            old_expense = copy.deepcopy(expense)

            if expense['status']['text'] == "draft" and \
                    data.get('status', '') != 'draft' and \
                    'ready' in data.get('status', ''):
                min_amount = self._process_expense_min_amount(
                    data.get('cost_type', expense['cost_type']))
                if min_amount == 0 or \
                        min_amount <= data.get('amount', expense['amount']):
                    data['status'] = "ready_for_manager"
                else:
                    data['status'] = "ready_for_creditor"

            allowed_fields, allowed_statuses = self._prepare_context_update_expense(expense)

            if not allowed_fields or not allowed_statuses:
                return make_response(jsonify('The content of this method is not valid'), 403)

            try:
                BusinessRulesEngine().process_rules(data, expense['employee']['afas_data'])
                data['manager_type'] = self._process_expense_manager_type(
                    data['cost_type'] if 'cost_type' in data else
                    expense['cost_type'])
            except ValueError as exception:
                return make_response(jsonify(str(exception)), 400)

            valid_update = self._update_expenses(data, allowed_fields, allowed_statuses, expense)

            if not valid_update:
                return make_response(jsonify('The content of this method is not valid'), 403)

            self.expense_journal(old_expense, expense)

            if data['status'] == 'rejected_by_manager' or data['status'] == 'rejected_by_creditor':
                self.send_notification('mail',
                                       'edit_expense',
                                       expense['employee']['afas_data'],
                                       expense.key.id_or_name)

            return make_response(jsonify(None), 200)

    def _update_expenses(self, data, allowed_fields, allowed_statuses, expense):
        items_to_update = list(allowed_fields.intersection(set(data.keys())))
        need_to_save = False
        for item in items_to_update:
            if item == "rnote":
                need_to_save = True
                expense["status"]["rnote"] = data[item]
            elif item != "status" and expense.get(item, None) != data[item]:
                need_to_save = True
                expense[item] = data[item]

        if 'status' in items_to_update:
            logger.debug(
                f"Employee status to update [{data['status']}] old [{expense['status']['text']}], legal "
                f"transition [{allowed_statuses}]")
            if data['status'] in allowed_statuses:
                need_to_save = True
                self._process_status_text_update(data['status'], expense)
            else:
                logging.info(
                    "Rejected unauthorized status transition for " +
                    f"{expense.key.id_or_name}: {expense['status']['text']} " +
                    f"> {data['status']}")
                return False

        if need_to_save:
            self.ds_client.put(expense)
            return True

        return False

    def update_exported_expenses(self, expenses_exported, document_time):
        """
        Do some sanity changed to keep data updated.
        :param document_type: A Payment or a booking file
        :param expenses_exported: Expense <Entity Keys>
        :param document_date: Date when it was exported
        """

        for exp in expenses_exported:
            with self.ds_client.transaction():
                expense = self.ds_client.get(self.ds_client.key("Expenses", exp.id))
                expense["status"]["export_date"] = document_time
                expense["status"]["text"] = "exported"
                self.ds_client.put(expense)

    @staticmethod
    def get_iban_details(iban):
        """
        Get the needed IBAN numbers of any dutch rekening number
        :param iban:
        :return:
        """
        detail = iban.replace(" ", "")

        if len(detail) > 8:
            bank_code = detail[4:8]
            bank_data = config.BIC_NUMBERS
            bic = next((r["bic"] for r in bank_data if r["identifier"] == bank_code), None)
        else:
            bic = None

        if bic:
            return bic

        return (
            "NOTPROVIDED"
        )  # Bank will determine the BIC based on the Debtor Account

    def filter_expenses_to_export(self):
        """
        Query the expenses to return desired values
        :return:
        """

        never_exported = []
        expenses_query = self.ds_client.query(kind="Expenses")
        for entity in expenses_query.fetch():
            if entity["status"]["text"] in EXPORTABLE_STATUSES:
                never_exported.append(entity)

        return never_exported

    def create_booking_and_payment_file(self):
        # make a selection of expenses to export
        expense_claims_to_export = self.filter_expenses_to_export()

        # if nothing to report, return immediate
        if not expense_claims_to_export:
            return {"Info": "No Exports Available"}, 200

        now = datetime.datetime.utcnow()

        local_tz = pytz.timezone(VWT_TIME_ZONE)
        local_now = now.replace(tzinfo=pytz.utc).astimezone(local_tz)

        export_file_name = now.strftime('%Y%m%d%H%M%S')

        result = self.create_booking_file(expense_claims_to_export, export_file_name, local_now)
        result = self.create_payment_file(expense_claims_to_export, export_file_name, local_now)

        if not result[0]:
            return {"Info": "Failed to upload payment file"}, 503

        retval = {"file_list": [
            {"booking_file": f"{api_base_url()}finances/expenses/documents/{export_file_name}/kinds/booking_file",
             "payment_file": f"{api_base_url()}finances/expenses/documents/{export_file_name}/kinds/payment_file",
             "export_date": now.isoformat(timespec="seconds") + 'Z'}]}

        self.update_exported_expenses(expense_claims_to_export, now)

        return retval, 200

    def create_booking_file(self, expense_claims_to_export, export_filename, document_date):
        """
        Create a booking file
        :return:
        """
        booking_file_data = []
        for expense_detail in expense_claims_to_export:
            # try:
            #     department_number_aka_afdeling_code = expense_detail["employee"][
            #         "afas_data"
            #     ]["Afdeling Code"]
            # except Exception:
            #     department_number_aka_afdeling_code = 0000
            # company_number = self.ds_client.get(
            #     self.ds_client.key(
            #         "Departments", department_number_aka_afdeling_code
            #     )
            # )
            logger.debug(f" transaction date [{expense_detail['transaction_date']}]")

            trans_date = dateutil.parser.parse(expense_detail['transaction_date']).strftime('%d-%m-%Y')

            boekingsomschrijving_bron = f"{expense_detail['employee']['afas_data']['Personeelsnummer']} {trans_date}"

            expense_detail["boekingsomschrijving_bron"] = boekingsomschrijving_bron

            cost_type_split = expense_detail["cost_type"].split(":")

            booking_file_data.append(
                {
                    "BoekingsomschrijvingBron": boekingsomschrijving_bron,
                    "Document-datum": document_date.strftime("%d%m%Y"),
                    "Boekings-jaar": document_date.strftime("%Y"),
                    "Periode": document_date.strftime("%m"),
                    "Bron-bedrijfs-nummer": config.BOOKING_FILE_STATICS["Bron-bedrijfs-nummer"],
                    "Bron gr boekrek": config.BOOKING_FILE_STATICS["Bron-grootboek-rekening"],
                    "Bron Org Code": config.BOOKING_FILE_STATICS["Bron-org-code"],
                    "Bron Process": "000",
                    "Bron Produkt": "000",
                    "Bron EC": "000",
                    "Bron VP": "00",
                    "Doel-bedrijfs-nummer": config.BOOKING_FILE_STATICS["Doel-bedrijfs-nummer"],
                    "Doel-gr boekrek": cost_type_split[1] if len(cost_type_split) >= 2 else "",
                    "Doel Org code": config.BOOKING_FILE_STATICS["Doel-org-code"],
                    "Doel Proces": "000",
                    "Doel Produkt": "000",
                    "Doel EC": "000",
                    "Doel VP": "00",
                    "D/C": "C",
                    "Bedrag excl. BTW": expense_detail["amount"],
                    "BTW-Bedrag": "0,00",
                }
            )

        booking_file = pd.DataFrame(booking_file_data).to_csv(
            sep=";", index=False, decimal=","
        )

        # Save File to CloudStorage
        bucket = self.cs_client.get_bucket(self.bucket_name)

        blob = bucket.blob(
            f"exports/booking_file/{document_date.year}/{document_date.month}/{document_date.day}/{export_filename}"
        )

        blob.upload_from_string(booking_file, content_type="text/csv")

        return True, export_filename, booking_file

    def _gather_creditor_name(self, expense):
        return expense["employee"]["afas_data"].get("Naam")

    def create_payment_file(self, expense_claims_to_export, export_filename, document_time):

        """
        Creates an XML file from claim expenses that have been exported. Thus a claim must have a status
        ==> status -- 'booking-file-created'
        """
        booking_timestamp_id = document_time.strftime("%Y%m%d%H%M%S")

        message_id = f"200/DEC/{booking_timestamp_id}"
        payment_info_id = f"200/DEC/{booking_timestamp_id}"

        # Set namespaces
        ET.register_namespace("", "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03")
        root = ET.Element(
            "{urn:iso:std:iso:20022:tech:xsd:pain.001.001.03}Document"
        )

        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

        customer_header = ET.SubElement(root, "CstmrCdtTrfInitn")
        expense_claims_to_export
        ctrl_sum = 0

        for expense in expense_claims_to_export:
            ctrl_sum += expense['amount']

        # Group Header
        header = ET.SubElement(customer_header, "GrpHdr")
        ET.SubElement(header, "MsgId").text = message_id
        ET.SubElement(header, "CreDtTm").text = document_time.isoformat(timespec="seconds")
        ET.SubElement(header, "NbOfTxs").text = str(
            len(expense_claims_to_export)  # Number Of Transactions in the batch
        )
        ET.SubElement(header, "CtrlSum").text = str(ctrl_sum)  # Total amount of the batch
        initiating_party = ET.SubElement(header, "InitgPty")
        ET.SubElement(initiating_party, "Nm").text = config.OWN_ACCOUNT["bedrijf"]

        #  Payment Information
        payment_info = ET.SubElement(customer_header, "PmtInf")
        ET.SubElement(payment_info, "PmtInfId").text = message_id
        ET.SubElement(payment_info, "PmtMtd").text = "TRF"  # Standard Value
        ET.SubElement(payment_info, "NbOfTxs").text = str(
            len(expense_claims_to_export)  # Number Of Transactions in the batch
        )
        ET.SubElement(payment_info, "CtrlSum").text = str(ctrl_sum)  # Total amount of the batch

        # Payment Type Information
        payment_typ_info = ET.SubElement(payment_info, "PmtTpInf")
        ET.SubElement(payment_typ_info, "InstrPrty").text = "NORM"
        payment_tp_service_level = ET.SubElement(payment_typ_info, "SvcLvl")
        ET.SubElement(payment_tp_service_level, "Cd").text = "SEPA"

        ET.SubElement(payment_info, "ReqdExctnDt").text = document_time.date().isoformat()

        # Debitor Information
        payment_debitor_info = ET.SubElement(payment_info, "Dbtr")
        ET.SubElement(payment_debitor_info, "Nm").text = "VWT BV"
        payment_debitor_account = ET.SubElement(payment_info, "DbtrAcct")
        payment_debitor_account_id = ET.SubElement(payment_debitor_account, "Id")
        ET.SubElement(payment_debitor_account_id, "IBAN").text = config.OWN_ACCOUNT[
            "iban"
        ]

        # Debitor Agent Tags Information
        payment_debitor_agent = ET.SubElement(payment_info, "DbtrAgt")
        payment_debitor_agent_id = ET.SubElement(
            payment_debitor_agent, "FinInstnId"
        )
        ET.SubElement(payment_debitor_agent_id, "BIC").text = config.OWN_ACCOUNT[
            "bic"
        ]
        for expense in expense_claims_to_export:
            # Transaction Transfer Information
            transfer = ET.SubElement(payment_info, "CdtTrfTxInf")
            transfer_payment_id = ET.SubElement(transfer, "PmtId")
            ET.SubElement(transfer_payment_id, "InstrId").text = payment_info_id
            ET.SubElement(transfer_payment_id, "EndToEndId").text = expense["boekingsomschrijving_bron"]

            # Amount
            amount = ET.SubElement(transfer, "Amt")
            ET.SubElement(amount, "InstdAmt", Ccy="EUR").text = str(expense["amount"])
            ET.SubElement(transfer, "ChrgBr").text = "SLEV"

            # Creditor Agent Tag Information
            amount_agent = ET.SubElement(transfer, "CdtrAgt")
            payment_creditor_agent_id = ET.SubElement(amount_agent, "FinInstnId")
            ET.SubElement(
                payment_creditor_agent_id, "BIC"
            ).text = self.get_iban_details(expense["employee"]["afas_data"]["IBAN"])

            # Creditor name
            creditor_name = ET.SubElement(transfer, "Cdtr")
            ET.SubElement(creditor_name, "Nm").text = self._gather_creditor_name(expense)

            # Creditor Account
            creditor_account = ET.SubElement(transfer, "CdtrAcct")
            creditor_account_id = ET.SubElement(creditor_account, "Id")

            # <ValidationPass> on whitespaces
            ET.SubElement(creditor_account_id, "IBAN").text = \
                expense["employee"]["afas_data"]["IBAN"].replace(" ", "")

            # Remittance Information
            remittance_info = ET.SubElement(transfer, "RmtInf")
            ET.SubElement(remittance_info, "Ustrd").text = expense["boekingsomschrijving_bron"]

        payment_xml_string = ET.tostring(root, encoding="utf8", method="xml")

        # Save File to CloudStorage
        bucket = self.cs_client.get_bucket(self.bucket_name)
        blob = bucket.blob(
            f"exports/payment_file/{document_time.year}/{document_time.month}/{document_time.day}/{export_filename}"
        )
        blob.upload_from_string(payment_xml_string, content_type="application/xml")

        payment_file = MD.parseString(payment_xml_string).toprettyxml(
            encoding="utf-8"
        )

        if config.POWER2PAY_URL:
            if not self.send_to_power2pay(payment_xml_string):
                return False, None, jsonify({"Info": "Failed to upload payment file"})

            logger.info("Power2Pay upload successful")
        else:
            logger.warning("Sending to Power2Pay is disabled")

        return True, export_filename, payment_file

    def send_to_power2pay(self, payment_xml_string):
        # Upload file to Power2Pay
        client = kms_v1.KeyManagementServiceClient()
        # Get the passphrase for the private key
        pk_passphrase = client.crypto_key_path_path(os.environ['GOOGLE_CLOUD_PROJECT'], 'europe-west1',
                                                    os.environ['GOOGLE_CLOUD_PROJECT'] + '-keyring',
                                                    config.POWER2PAY_KEY_PASSPHRASE)
        response = client.decrypt(pk_passphrase, open('passphrase.enc', "rb").read())
        passphrase = response.plaintext.decode("utf-8").replace('\n', '')
        # Get the private key and decode using passphrase
        pk_enc = client.crypto_key_path_path(os.environ['GOOGLE_CLOUD_PROJECT'], 'europe-west1',
                                             os.environ['GOOGLE_CLOUD_PROJECT'] + '-keyring', config.POWER2PAY_KEY)
        response = client.decrypt(pk_enc, open('power2pay-pk.enc', "rb").read())
        # Write un-encrypted key to file (for requests library)
        pk = crypto.load_privatekey(crypto.FILETYPE_PEM, response.plaintext, passphrase.encode())

        temp_key_file = tempfile.NamedTemporaryFile(mode='w', delete=False)
        temp_key_file.write(str(crypto.dump_privatekey(crypto.FILETYPE_PEM, pk, cipher=None, passphrase=None), 'utf-8'))
        temp_key_file.close()

        # Create the HTTP POST request
        cert_file_path = "power2pay-cert.pem"
        cert = (cert_file_path, temp_key_file.name)

        r = requests.post(config.POWER2PAY_URL, data=payment_xml_string, cert=cert, verify=True)

        logger.info(f"Power2Pay send result {r.status_code}: {r.content}")
        return r.ok

    def get_all_documents_list(self):
        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)

        all_exports_files = {'file_list': []}
        blobs = expenses_bucket.list_blobs(
            prefix=f"exports/booking_file"
        )

        for blob in blobs:
            name = blob.name.split('/')[-1]

            all_exports_files['file_list'].append({
                "export_date": datetime.datetime.strptime(name, '%Y%m%d%H%M%S'),
                "booking_file": f"{api_base_url()}finances/expenses/documents/{name}/kinds/booking_file",
                "payment_file": f"{api_base_url()}finances/expenses/documents/{name}/kinds/payment_file"
            })

        all_exports_files['file_list'] = sorted(all_exports_files['file_list'], key=lambda k: k['export_date'],
                                                reverse=True)
        return all_exports_files

    def get_single_document_reference(self, document_id, document_type):
        document_date = datetime.datetime.strptime(document_id, '%Y%m%d%H%M%S')
        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)

        blob = expenses_bucket.blob(
            f"exports/{document_type}/{document_date.year}/{document_date.month}/{document_date.day}/{document_id}"
        )

        if blob.exists():
            with tempfile.NamedTemporaryFile(delete=False) as export_file:
                blob.download_to_file(export_file)
                export_file.close()
            return export_file

    def _create_expenses_query(self):
        return self.ds_client.query(kind="Expenses", order=["-claim_date"])

    def _create_cost_types_list(self, field):
        cost_types = {}
        for cost_type in datastore.Client().query(kind="CostTypes").fetch():
            if field in cost_type:
                cost_types[cost_type['Grootboek']] = cost_type[field]

        return cost_types

    def _process_cost_type(self, cost_type, cost_types_list):
        grootboek_number = re.search("[0-9]{6}", cost_type)
        if grootboek_number and grootboek_number.group() in cost_types_list:
            return cost_types_list[grootboek_number.group()]

        return None

    def _process_expense_manager_type(self, cost_type):
        cost_types_list = self._create_cost_types_list('ManagerType')
        manager_type = self._process_cost_type(cost_type, cost_types_list)

        return 'linemanager' if manager_type is None else manager_type

    def _process_expense_min_amount(self, cost_type):
        cost_types_list = self._create_cost_types_list('MinAmount')
        min_amount = self._process_cost_type(cost_type, cost_types_list)

        return 50 if min_amount is None else min_amount

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
                    "claim_date": ed["claim_date"],
                    "transaction_date": ed["transaction_date"],
                    "employee": ed["employee"]["full_name"],
                    "status": ed["status"],
                }
                for ed in expenses_data
            ])

        return make_response(jsonify(None), 204)

    def expense_journal(self, old_expense, expense):
        changed = []

        def default(o):
            if isinstance(o, (datetime.date, datetime.datetime)):
                return o.isoformat(timespec="seconds") + 'Z'

        for attribute in list(set(old_expense) | set(expense)):
            if attribute not in old_expense:
                changed.append({attribute: {"new": expense[attribute]}})
            elif old_expense[attribute] != expense[attribute]:
                changed.append({attribute: {"old": old_expense[attribute], "new": expense[attribute]}})
            elif attribute not in expense:
                changed.append({attribute: {"old": old_expense[attribute], "new": None}})

        key = self.ds_client.key("Expenses_Journal")
        entity = datastore.Entity(key=key)
        entity.update(
            {
                "Expenses_Id": expense.key.id,
                "Time": datetime.datetime.utcnow().isoformat(timespec="seconds") + 'Z',
                "Attributes_Changed": json.dumps(changed, default=default),
                "User": self.employee_info["unique_name"],
            }
        )
        self.ds_client.put(entity)

    def send_message_internal(self, user_id, message, expense_id):
        try:
            message = (self.gmail_service.users().messages().send(
                userId=user_id, body=message).execute())
            logging.info(
                f"Email '{message['id']}' for expense '{expense_id}' " +
                "has been sent")
        except errors.HttpError as error:
            logging.error('An error occurred: %s' % error)

    def create_message(self, to, mail_body):
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = config.GMAIL_SENDER_ADDRESS
            msg['Subject'] = mail_body['subject']
            msg['Reply-To'] = mail_body['reply_to']
            msg['To'] = to

            with open('gmail_template.html', 'r') as mail_template:
                msg_html = mail_template.read()

            msg_html = msg_html.replace('$MAIL_TITLE',
                                        mail_body['title'])
            msg_html = msg_html.replace('$MAIL_BODY',
                                        mail_body['body'])

            msg.attach(MIMEText(msg_html, 'html'))
            raw = base64.urlsafe_b64encode(msg.as_bytes())
            raw = raw.decode()
            body = {'raw': raw}
            return body
        except Exception as error:
            logging.error('An error occurred: %s' % error)

    def send_message(self, expense_id, to, mail_body):
        new_message = self.create_message(to, mail_body)
        self.send_message_internal("me", new_message, expense_id)

    def send_notification(self, notification_type, message_type, afas_data, expense_id):
        if notification_type == 'mail':
            self.send_email_notification(message_type, afas_data, expense_id)
        else:
            logging.warning("No notification type specified")

    def send_email_notification(self, mail_type, afas_data, expense_id):
        try:
            if hasattr(config, 'GMAIL_STATUS') and config.GMAIL_STATUS:
                mail_body = None
                recipient = None

                if mail_type == 'add_expense' and \
                        'Manager_personeelsnummer' in afas_data:
                    query = self.ds_client.query(kind='AFAS_HRM')
                    query.add_filter('Personeelsnummer', '=',
                                     afas_data['Manager_personeelsnummer'])
                    db_data = list(query.fetch(limit=1))

                    if len(db_data) == 1 and 'email_address' in db_data[0]:
                        recipient = db_data[0]

                    mail_body = {
                        'subject': 'Er staat een nieuwe declaratie voor je klaar!',
                        'title': 'Nieuwe declaratie',
                        'text': "Er staat een nieuwe declaratie voor je klaar " +
                                "in de Declaratie-app, log in om deze " +
                                "te beoordelen."
                    }
                elif mail_type == 'edit_expense' and 'email_address' in afas_data:
                    recipient = afas_data
                    mail_body = {
                        'subject': 'Een declaratie heeft aanpassingen nodig!',
                        'title': 'Aanpassing vereist',
                        'text': "Een ingediende declaratie heeft wijzigingen " +
                                "nodig in de Declaratie-app, log in om deze " +
                                "aan te passen."
                    }

                if mail_body and recipient:
                    logging.info(f"Creating email for expense '{expense_id}'")
                    recipient_name = recipient['Voornaam'] \
                        if 'Voornaam' in recipient else 'ontvanger'

                    mail_body['body'] = """Beste {},<br /><br />
                        {}
                        Mochten er nog vragen zijn, mail gerust naar
                        <a href="mailto:{}?subject=Declaratie-app%20%7C%20Nieuwe Declaratie">{}</a>.<br /><br />
                        Met vriendelijke groeten,<br />FSSC""".format(
                        recipient_name, mail_body['text'],
                        config.GMAIL_ADDEXPENSE_REPLYTO,
                        config.GMAIL_ADDEXPENSE_REPLYTO
                    )

                    mail_body['from'] = config.GMAIL_SENDER_ADDRESS
                    mail_body['reply_to'] = config.GMAIL_ADDEXPENSE_REPLYTO

                    del mail_body['text']

                    self.send_message(expense_id, recipient['email_address'],
                                      mail_body)
                else:
                    logging.info(
                        f"No mail info found for expense '{expense_id}'")
            else:
                logging.info("Dev mode active for sending e-mails")
        except Exception as error:
            logging.exception(
                f'An exception occurred when sending an email: {error}')


class EmployeeExpenses(ClaimExpenses):
    def __init__(self, employee_id):
        super().__init__()
        self.employee_id = employee_id

    def _check_attachment_permission(self, expense):
        if expense["employee"]["email"] != self.employee_info["unique_name"]:
            return False

        return True

    def get_all_expenses(self):
        expenses_info = self._create_expenses_query()
        expenses_info.add_filter(
            "employee.afas_data.email_address", "=", self.employee_info["unique_name"]
        )
        return self._process_expenses_info(expenses_info)

    def _prepare_context_update_expense(self, expense):
        # Check if expense is from employee
        if not expense["employee"]["email"] == \
               self.employee_info["unique_name"]:
            return {}, {}

        # Check if status update is not unauthorized
        allowed_status_transitions = {
            'draft': ['draft', 'ready_for_manager', 'ready_for_creditor', 'cancelled'],
            'rejected_by_manager': ['ready_for_manager', 'ready_for_creditor', 'cancelled'],
            'rejected_by_creditor': ['ready_for_manager', 'ready_for_creditor', 'cancelled']
        }

        if expense['status']['text'] in allowed_status_transitions:
            fields = {
                "status",
                "cost_type",
                "rnote",
                "note",
                "transaction_date",
                "amount",
                "manager_type"
            }
            return fields, allowed_status_transitions[expense['status']['text']]

        return {}, {}

    def add_attachment(self, expense_id, data):
        expense_key = self.ds_client.key("Expenses", expense_id)
        expense = self.ds_client.get(expense_key)
        if not expense:
            return make_response(jsonify('Attempt to add attachment to undefined expense claim', 400))
        if expense["employee"]["email"] != self.employee_info["unique_name"]:
            return make_response(jsonify('Unauthorized'), 403)

        creation = self.create_attachment(
            data,
            expense.key.id_or_name,
            self.employee_info["unique_name"]
        )

        if not creation:
            return jsonify('Some data was missing or incorrect'), 400
        return 201


class ManagerExpenses(ClaimExpenses):
    def _check_attachment_permission(self, expense):
        if 'leasecoordinator.write' in \
                self.employee_info.get('scopes', []) and \
                self._process_expense_manager_type(
                    expense['cost_type']) == 'leasecoordinator':
            return True

        return expense["employee"]["afas_data"]["Manager_personeelsnummer"] == self.get_manager_identifying_value()

    def _process_expenses_info(self, expenses_info):
        expenses_data = expenses_info.fetch()
        if expenses_data:
            return [
                {
                    "id": ed.id,
                    "amount": ed["amount"],
                    "note": ed["note"],
                    "cost_type": ed["cost_type"],
                    "claim_date": ed["claim_date"],
                    "transaction_date": ed["transaction_date"],
                    "employee": ed["employee"]["full_name"],
                    "status": ed["status"],
                    "manager_type": ed.get("manager_type")
                }
                for ed in expenses_data
            ]
        return []

    def __init__(self):
        super().__init__()

    def get_manager_identifying_value(self):
        afas_data = self.get_employee_afas_data(self.employee_info["unique_name"])
        if afas_data:
            return afas_data["Personeelsnummer"]

        return None

    def get_all_expenses(self):
        expense_data = []

        # Retrieve manager's expenses
        expenses_info = self._create_expenses_query()
        expenses_info.add_filter("status.text", "=", "ready_for_manager")
        expenses_info.add_filter(
            "employee.afas_data.Manager_personeelsnummer", "=",
            self.get_manager_identifying_value())

        for expense in self._process_expenses_info(expenses_info):
            if 'manager_type' in expense and \
                    expense['manager_type'] == 'leasecoordinator':
                continue

            expense_data.append(expense)

        # Retrieve lease coordinator's expenses if correct role
        if 'leasecoordinator.write' in self.employee_info.get('scopes', []):
            expenses_lease = self._create_expenses_query()
            expenses_lease.add_filter("manager_type", "=", "leasecoordinator")
            expenses_lease.add_filter("status.text", "=", "ready_for_manager")

            expense_data = expense_data + self._process_expenses_info(
                expenses_lease)

            expense_data.sort(key=lambda x: x['claim_date'], reverse=True)

        if expense_data:
            return jsonify(expense_data)

        return make_response(jsonify(None), 204)

    def _prepare_context_update_expense(self, expense):
        # Check if expense is for manager
        if not expense["employee"]["afas_data"]["Manager_personeelsnummer"] == \
               self.get_manager_identifying_value() and \
                'leasecoordinator.write' not in self.employee_info.get('scopes', []):
            return {}, {}

        # Check if status update is not unauthorized
        allowed_status_transitions = {
            'ready_for_manager': ['ready_for_creditor', 'rejected_by_manager']
        }

        if expense['status']['text'] in allowed_status_transitions:
            fields = {
                "status",
                "cost_type",
                "rnote",
                "manager_type"
            }
            return fields, allowed_status_transitions[expense['status']['text']]

        return {}, {}


class ControllerExpenses(ClaimExpenses):
    def _check_attachment_permission(self, expense):
        return True

    def __init__(self):
        super().__init__()

    def get_all_expenses(self):
        """Get JSON of all the expenses"""

        expenses_info = self.ds_client.query(kind="Expenses")

        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = []
            for ed in expenses_data:
                logging.debug(f'get_all_expenses: [{ed}]')
                results.append({
                    "id": ed.id,
                    "amount": ed["amount"],
                    "note": ed["note"],
                    "cost_type": ed["cost_type"],
                    "claim_date": ed["claim_date"],
                    "transaction_date": ed["transaction_date"],
                    "employee": ed["employee"]["full_name"],
                    "status": ed["status"],
                })
            return jsonify(results)

        return make_response(jsonify(None), 204)

    def _prepare_context_update_expense(self, expense):
        return {}, {}


class CreditorExpenses(ClaimExpenses):
    def _check_attachment_permission(self, expense):
        return True

    def __init__(self):
        super().__init__()

    def get_all_expenses(self, expenses_list, date_from, date_to):
        """Get JSON/CSV of all the expenses"""
        day_from = "1970-01-01T00:00:00Z"
        day_to = datetime.datetime.utcnow().isoformat(timespec="seconds") + 'Z'

        if date_from != '':
            day_from = date_from + "T00:00:00Z"
        if date_to != '':
            day_to = date_to + "T23:59:59Z"

        if date_from > date_to:
            return make_response(jsonify("Start date is later than end date"), 403)

        expenses_ds = self.ds_client.query(kind="Expenses")
        expenses_ds.add_filter("claim_date", ">=", day_from)
        expenses_ds.add_filter("claim_date", "<=", day_to)
        expenses_data = expenses_ds.fetch()

        query_filter: Dict[Any, str] = dict(creditor="ready_for_creditor", creditor2="approved")

        if expenses_data:
            results = []

            for expense in expenses_data:
                expense_row = {
                    "id": expense.id,
                    "amount": expense["amount"],
                    "note": expense["note"],
                    "cost_type": expense["cost_type"],
                    "claim_date": expense["claim_date"],
                    "transaction_date": expense["transaction_date"],
                    "employee": expense["employee"]["full_name"],
                    "status": expense["status"],
                    "auto_approved": expense.get("auto_approved", ""),
                    "rnote": expense.get("status", {}).get("rnote", ""),
                    "manager": expense.get("employee", {}).get("afas_data", {}).get(
                        "Manager_personeelsnummer", "Manager not found: check expense"),
                    "export_date": expense["status"].get("export_date", "")
                }

                expense_row["export_date"] = (expense_row["export_date"], "")[expense_row["export_date"] == "never"]

                if expenses_list == "expenses_creditor":
                    if (query_filter["creditor"] == expense["status"]["text"] or
                            query_filter["creditor2"] == expense["status"]["text"]):
                        results.append(expense_row)

                if expenses_list == "expenses_all":
                    results.append(expense_row)

            return results

        return make_response(jsonify("No expenses to return"), 204)

    def get_all_expenses_journal(self, date_from, date_to):
        """Get CSV of all the expenses from Expenses_Journal"""
        day_from = "1970-01-01T00:00:00Z"
        day_to = datetime.datetime.utcnow().isoformat(timespec="seconds") + 'Z'

        if date_from != '':
            day_from = date_from + "T00:00:00Z"
        if date_to != '':
            day_to = date_to + "T23:59:59Z"

        if date_from > date_to:
            return make_response(jsonify("Start date is later than end date"), 403)

        expenses_ds = self.ds_client.query(kind="Expenses_Journal")
        expenses_ds.add_filter("Time", ">=", day_from)
        expenses_ds.add_filter("Time", "<=", day_to)
        expenses_data = expenses_ds.fetch()

        if expenses_data:
            results = []

            for expense in expenses_data:
                if expense["Attributes_Changed"] != "[]":
                    results += self.expense_changes(expense)
            return results

        return make_response(jsonify("No expenses to return"), 204)

    def expense_changes(self, expense):
        """

        :param expense:
        :return: all changes of an expense
        """
        changes = []
        list_attributes = json.loads(expense["Attributes_Changed"])
        for attribute in list_attributes:
            for name in attribute:
                # Handle nested components: different row per component
                if isinstance((attribute[name]["new"]), dict):
                    try:
                        if "old" in attribute[name] and isinstance(attribute[name]["old"], dict):
                            for component in attribute[name]["new"]:
                                # Expense has a new component which does not have a 'new' value
                                if component not in attribute[name]["old"]:
                                    changes.append({
                                        "Expenses_Id": expense["Expenses_Id"],
                                        "Time": expense["Time"],
                                        "Attribute": name + ": " + component,
                                        "Old value": "",
                                        "New value": str(attribute[name]["new"][component]),
                                        "User": expense.get("User", "")
                                    })
                                # Expense has an old value which differs from the new value
                                elif attribute[name]["new"][component] != attribute[name]["old"][component]:
                                    changes.append({
                                        "Expenses_Id": expense["Expenses_Id"],
                                        "Time": expense["Time"],
                                        "Attribute": name + ": " + component,
                                        "Old value": str(attribute[name]["old"][component]),
                                        "New value": str(attribute[name]["new"][component]),
                                        "User": expense.get("User", "")
                                    })
                        # Expense is completely new
                        else:
                            for component in attribute[name]["new"]:
                                if component == "afas_data":
                                    continue
                                changes.append({
                                    "Expenses_Id": expense["Expenses_Id"],
                                    "Time": expense["Time"],
                                    "Attribute": name + ": " + component,
                                    "Old value": "",
                                    "New value": str(attribute[name]["new"][component]),
                                    "User": expense.get("User", "")
                                })

                    except (TypeError, KeyError):
                        logging.warning("Expense from Expense_Journal does not have the right format: {}".
                                        format(expense["Expenses_Id"]))
                # Expense has an old value which differs from the new value and no nested components
                else:
                    old_value = ""
                    if "old" in attribute[name]:
                        old_value = str(attribute[name]["old"])

                    changes.append({
                        "Expenses_Id": expense["Expenses_Id"],
                        "Time": expense["Time"],
                        "Attribute": name,
                        "Old value": old_value,
                        "New value": str(attribute[name]["new"]),
                        "User": expense.get("User", "")
                    })

        return changes

    def _prepare_context_update_expense(self, expense):
        # Check if status update is not unauthorized
        allowed_status_transitions = {
            'ready_for_creditor': ['rejected_by_creditor', 'approved']
        }

        if expense['status']['text'] in allowed_status_transitions:
            fields = {
                "status",
                "cost_type",
                "rnote",
                "manager_type"
            }
            return fields, allowed_status_transitions[expense['status']['text']]

        return {}, {}


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
            if form_data.to_dict().get('transaction_date').replace(tzinfo=None) <= \
                    (datetime.datetime.today() + datetime.timedelta(hours=2)).replace(tzinfo=None):
                html = {
                    '"': "&quot;",
                    "&": "&amp;",
                    "'": "&apos;",
                    ">": "&gt;",
                    "<": "&lt;",
                    "{": "&lbrace;",
                    "}": "&rbrace;"
                }
                form_data.note = "".join(html.get(c, c) for c in form_data.to_dict().get('note'))
                form_data.transaction_date = form_data.transaction_date.strftime('%Y-%m-%dT%H:%M:%S.000Z')
                return expense_instance.add_expenses(form_data)
            return jsonify('Date needs to be in the past'), 400
    except Exception:
        logging.exception('Exception on add_expense')
        return jsonify("Something went wrong. Please try again later"), 500


def get_all_creditor_expenses(expenses_list, date_from, date_to):
    """
    Get all expenses
    :rtype: None
    """
    if expenses_list not in ["expenses_creditor", "expenses_all"]:
        return make_response(jsonify("Not a valid query parameter"), 400)

    expense_instance = CreditorExpenses()
    expenses_data = expense_instance.get_all_expenses(expenses_list=expenses_list, date_from=date_from, date_to=date_to)

    format_expense = connexion.request.headers['Accept']

    return get_expenses_format(expenses_data=expenses_data, format_expense=format_expense)


def get_all_creditor_expenses_journal(date_from, date_to):
    """
    Get all expenses journal
    :rtype: None
    """
    expense_instance = CreditorExpenses()
    expenses_data = expense_instance.get_all_expenses_journal(date_from=date_from, date_to=date_to)

    format_expense = connexion.request.headers["Accept"]

    return get_expenses_format(expenses_data=expenses_data, format_expense=format_expense)


def get_cost_types():  # noqa: E501
    """Get all cost_type
    :rtype: None
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_cost_types()


def get_document(document_id, document_type):
    """
    Get a requested booking or payment file from a booking or payment identity in the format of
    1. Booking File => month_day_file_name => 7_12_12:34-12-07-2019
    2. Document File => month_day_file_name => 7_12_12:34-12-07-2019
    e.g => http://{HOST}/finances/expenses/documents/7_12_12:34-12-07-2019/kinds/payment_file
    :rtype: None
    :return"""

    expense_instance = ClaimExpenses()
    try:
        export_file = expense_instance.get_single_document_reference(
            document_id=document_id, document_type=document_type)
    except ValueError as e:
        return make_response(str(e), 400)
    except Exception as error:
        logging.exception(
            f'An exception occurred when retrieving a document: {error}')
        return make_response('Something went wrong', 500)
    else:
        if export_file:
            if document_type == 'payment_file':
                content_response = {
                    "content_type": "application/xml",
                    "file": MD.parse(export_file.name).toprettyxml(
                        encoding="utf-8").decode()
                }
            elif document_type == 'booking_file':
                with open(export_file.name, "r") as file_in:
                    content_response = {
                        "content_type": "text/csv",
                        "file": file_in.read()
                    }
                    file_in.close()

            mime_type = content_response['content_type']
            return Response(
                content_response["file"],
                headers={
                    "Content-Type": f"{mime_type}",
                    "charset": "utf-8",
                    "Content-Disposition": f"attachment; filename={document_id}.{mime_type.split('/')[1]}",
                    "Authorization": "",
                },
            )

        return make_response('Document not found', 404)


def get_expenses_format(expenses_data, format_expense):
    """
    Get format of expenses export: csv/json
    :param expenses_data:
    :param format_expense:
    :param extra_fields:
    :return:
    """
    if not expenses_data:
        return jsonify("No results with current filter"), 204

    if isinstance(expenses_data, Response):
        return expenses_data

    if "application/json" in format_expense:
        logging.debug("Creating json table")
        return jsonify(expenses_data)

    if "text/csv" in format_expense:
        logging.debug("Creating csv file")
        try:
            with tempfile.NamedTemporaryFile("w") as csv_file:
                count = 0
                for expense in expenses_data:
                    if count == 0:
                        field_names = list(expense.keys())
                        csv_writer = csv.DictWriter(csv_file, fieldnames=field_names)
                        csv_writer.writeheader()
                        count = 1

                    if "status" in expense:
                        expense["status"] = expense["status"]["text"]

                    csv_writer.writerow(expense)
                csv_file.flush()
                return send_file(csv_file.name,
                                 mimetype='text/csv',
                                 as_attachment=True,
                                 attachment_filename='tmp.csv')
        except Exception:
            logging.exception('Exception on writing/sending CSV in get_all_expenses')
            return jsonify("Something went wrong"), 500

    return jsonify("Request missing an Accept header"), 400


def get_document_list():
    """
    Get a list of all documents ever created
    :rtype: None
    :return"""

    expense_instance = ClaimExpenses()
    all_exports = expense_instance.get_all_documents_list()
    return jsonify(all_exports)


def create_booking_and_payment_file():
    expense_instance = ClaimExpenses()
    return expense_instance.create_booking_and_payment_file()


def get_managers_expenses():
    expense_instance = ManagerExpenses()
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


def update_expenses_creditor(expenses_id):
    """
    Update expense by expense_id with creditor permissions
    :rtype: Expenses
    """
    try:
        if connexion.request.is_json:
            form_data = json.loads(connexion.request.get_data().decode())
            expense_instance = CreditorExpenses()
            return expense_instance.update_expenses(expenses_id, form_data, True)
    except Exception:
        logging.exception('Exception on update_expenses_creditor')
        return jsonify("Something went wrong. Please try again later"), 500


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
            if form_data.get('transaction_date'):  # Check if date exists. If it doesn't, let if pass.
                if datetime.datetime.strptime(form_data.get('transaction_date'),
                                              '%Y-%m-%dT%H:%M:%S.%fZ') > datetime.datetime.today() \
                        + datetime.timedelta(hours=2):
                    return jsonify('Date needs to be in de past'), 400

            if form_data.get('note'):  # Check if note exists. If it doesn't, let if pass.
                html = {
                    '"': "&quot;",
                    "&": "&amp;",
                    "'": "&apos;",
                    ">": "&gt;",
                    "<": "&lt;",
                    "{": "&lbrace;",
                    "}": "&rbrace;"
                }
                form_data["note"] = "".join(html.get(c, c) for c in form_data.get('note'))

            return expense_instance.update_expenses(expenses_id, form_data)
    except Exception:
        logging.exception("Update exp")
        return jsonify("Something went wrong. Please try again later"), 500


def update_expenses_manager(expenses_id):
    """
    Update expense by expense_id with employee permissions
    :param expenses_id:
    :return:
    """
    try:
        if connexion.request.is_json:
            form_data = json.loads(connexion.request.get_data().decode())
            expense_instance = ManagerExpenses()
            return expense_instance.update_expenses(expenses_id, form_data, True)
    except Exception:
        logging.exception('Exception on update_expense')
        return jsonify("Something went wrong. Please try again later"), 500


def get_expenses_employee(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_expenses(expenses_id, "employee")


def get_expenses_creditor(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_expenses(expenses_id, "creditor")


def get_attachment_creditor(expenses_id):
    """
    Get attachment by expenses id
    :param expenses_id:
    :return:
    """
    expense_instance = CreditorExpenses()
    return expense_instance.get_attachment(expenses_id)


def get_attachment_manager(expenses_id):
    expense_instance = ManagerExpenses()
    return expense_instance.get_attachment(expenses_id)


def get_attachment_controllers(expenses_id):
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


def delete_attachment(expenses_id, attachments_name):
    """
    Delete attachment by expense id and attachment name
    :param expenses_id:
    :param attachments_name:
    :return:
    """
    expense_instance = ClaimExpenses()
    return expense_instance.delete_attachment(expenses_id, attachments_name)


def add_attachment_employee(expenses_id):
    try:
        if connexion.request.is_json:
            expense_instance = EmployeeExpenses(None)
            form_data = AttachmentData.from_dict(
                connexion.request.get_json()
            )  # noqa: E501
            return expense_instance.add_attachment(expenses_id, form_data)
    except Exception:
        logging.exception('Exception on add_attachment')
        return jsonify("Something went wrong. Please try again later"), 500


def api_base_url():
    base_url = request.host_url

    if 'GAE_INSTANCE' in os.environ:
        if hasattr(config, 'BASE_URL'):
            base_url = config.BASE_URL
        else:
            base_url = f"https://{os.environ['GOOGLE_CLOUD_PROJECT']}.appspot.com/"

    return base_url
