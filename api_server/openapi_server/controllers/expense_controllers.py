import base64
import copy
import json
import os
import requests
import re

import datetime
import mimetypes
import tempfile
import xml.etree.cElementTree as ET
import xml.dom.minidom as MD
from abc import abstractmethod
from io import BytesIO
from typing import Dict, Any
import dateutil


import pytz

import config
import logging
import pandas as pd

import connexion
import googleapiclient.discovery
from flask import make_response, jsonify, Response, g, request
from google.cloud import datastore, storage, kms_v1
from google.oauth2 import service_account
from apiclient import errors
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from openapi_server.models.attachment_data import AttachmentData
from openapi_server.models.expense_data import ExpenseData

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
        self.cs_client = storage.Client()  # CloudStore
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
        filename = f"{today.hour:02d}:{today.minute:02d}:{today.second:02d}-{today.year}{today.month}{today.day}" \
                   f"-{attachment.name}"
        bucket = self.cs_client.get_bucket(self.bucket_name)
        blob = bucket.blob(f"exports/attachments/{email_name}/{expenses_id}/{filename}")
        blob.upload_from_string(
            base64.b64decode(attachment.content.split(",")[1]),
            content_type=mimetypes.guess_type(attachment.content)[0],
        )

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
            return make_response(jsonify(None), 403)

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
                "content": stream_read.decode('utf-8'),
                "name": blob.name.split('/')[-1]
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
                logging.debug(f'get_all_expenses: [{ed}]')
                if 'status' in ed and (query_filter["creditor"] == ed["status"]["text"] or
                                       query_filter["creditor2"] == ed["status"]["text"]):
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
        else:
            return make_response(jsonify(None), 204)

    def add_expenses(self, data):
        """
        Add expense with given data amount and given data note. An expense can have one of 6
        statuses.
        Status Life Cycle:
        *** ready_for{role} => { rejected } <= approved => exported
        """
        if "unique_name" in self.employee_info.keys():
            if data.amount >= 50:
                ready_text = "ready_for_manager"
            else:
                ready_text = "ready_for_creditor"
            afas_data = self.get_employee_afas_data(self.employee_info["unique_name"])
            if afas_data:
                key = self.ds_client.key("Expenses")
                entity = datastore.Entity(key=key)
                entity.update(
                    {
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
                        "claim_date": datetime.datetime.utcnow().isoformat(timespec="seconds")+'Z',
                        "status": dict(export_date="never", text=ready_text),
                    }
                )
                self.ds_client.put(entity)

                if ready_text == 'ready_for_manager':
                    self.send_email_notification(
                        'add_expense', afas_data,
                        entity.key.id_or_name)

                return make_response(jsonify(entity.key.id_or_name), 201)
            else:
                return make_response(jsonify('Employee not found'), 403)
        else:
            return make_response(jsonify('Employee not unique'), 403)

    @abstractmethod
    def _process_status_text_update(self, item, expense):
        pass

    @abstractmethod
    def _process_status_amount_update(self, amount, expense):
        pass

    @abstractmethod
    def _prepare_context_update_expense(self, data, expense):
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
            fields, status = self._prepare_context_update_expense(data, expense)
            if fields and status:
                self._update_expenses(data, fields, status, expense)
                self.expense_journal(old_expense, expense)
                return make_response(jsonify(None), 200)
            else:
                return make_response(jsonify(None), 403)

    def _update_expenses(self, data, fields, status, expense):
        items_to_update = list(fields.intersection(set(data.keys())))
        need_to_save = False
        for item in items_to_update:
            if item == "status":
                logger.debug(f"Employee status to update [{data[item]}] old [{expense['status']['text']}], legal "
                             f"transition [{status}]")
                if data[item] in status:
                    need_to_save = True
                    self._process_status_text_update(data[item], expense)
            elif item == "rnote":
                need_to_save = True
                expense["status"]["rnote"] = data[item]
            elif item == "amount" and expense[item] != data[item]:
                need_to_save = True
                expense[item] = data[item]
                self._process_status_amount_update(data[item], expense)
            elif expense[item] != data[item]:
                need_to_save = True
                expense[item] = data[item]

        if need_to_save:
            self.ds_client.put(expense)

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
        else:
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
                      "export_date": now.isoformat(timespec="seconds")+'Z'}]}

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

        # Group Header
        header = ET.SubElement(customer_header, "GrpHdr")
        ET.SubElement(header, "MsgId").text = message_id
        ET.SubElement(header, "CreDtTm").text = document_time.isoformat(timespec="seconds")
        ET.SubElement(header, "NbOfTxs").text = str(
            len(expense_claims_to_export)  # Number Of Transactions in the batch
        )
        initiating_party = ET.SubElement(header, "InitgPty")
        ET.SubElement(initiating_party, "Nm").text = config.OWN_ACCOUNT["bedrijf"]

        #  Payment Information
        payment_info = ET.SubElement(customer_header, "PmtInf")
        ET.SubElement(payment_info, "PmtInfId").text = message_id
        ET.SubElement(payment_info, "PmtMtd").text = "TRF"  # Standard Value
        ET.SubElement(payment_info, "NbOfTxs").text = str(
            len(expense_claims_to_export)  # Number Of Transactions in the batch
        )

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

        payment_file_string = ET.tostring(root, encoding="utf8", method="xml")
        payment_file_name = f"/tmp/payment_file_{export_filename}"
        open(payment_file_name, "w").write(str(payment_file_string, 'utf-8'))

        # Save File to CloudStorage
        bucket = self.cs_client.get_bucket(self.bucket_name)

        blob = bucket.blob(
            f"exports/payment_file/{document_time.year}/{document_time.month}/{document_time.day}/{export_filename}"
        )

        # Upload file to Blob Storage
        blob.upload_from_string(payment_file_string, content_type="application/xml")

        #  Do some sanity routine

        payment_file = MD.parseString(payment_file_string).toprettyxml(
            encoding="utf-8"
        )

        if config.POWER2PAY_URL:
            if not self.send_to_power2pay(payment_file_name):
                return (False, None, jsonify({"Info": "Failed to upload payment file"}))
            else:
                logger.warning("Error sending to Power2Pay")
        else:
            logger.warning("Sending to Power2Pay is disabled")

        return (True, export_filename, payment_file)

    def send_to_power2pay(self, payment_file_name):
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
        key_file_path = "/tmp/key.pem"
        open(key_file_path, "w").write(
            str(crypto.dump_privatekey(crypto.FILETYPE_PEM, pk, cipher=None, passphrase=None), 'utf-8'))
        # Create the HTTP POST request
        cert_file_path = "power2pay-cert.pem"
        cert = (cert_file_path, key_file_path)
        xml_file = payment_file_name
        with open(xml_file) as xml:
            r = requests.post(config.POWER2PAY_URL, data=xml, cert=cert, verify=True)

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

        all_exports_files['file_list'] = sorted(all_exports_files['file_list'], key=lambda k: k['export_date'], reverse=True)
        return all_exports_files

    def get_single_document_reference(self, document_id, document_type):

        document_date = datetime.datetime.strptime(document_id, '%Y%m%d%H%M%S')
        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)

        with tempfile.NamedTemporaryFile(delete=False) as export_file:
            expenses_bucket.blob(
                f"exports/{document_type}/{document_date.year}/{document_date.month}/{document_date.day}/{document_id}"
            ).download_to_file(export_file)
            export_file.close()
            return export_file

    def _create_expenses_query(self):
        return self.ds_client.query(kind="Expenses", order=["-claim_date"])

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
        else:
            return make_response(jsonify(None), 204)

    def expense_journal(self, old_expense, expense):
        changed = []

        for attribute in list(set(list(old_expense)) & set(list(expense))):
            if old_expense[attribute] != expense[attribute]:
                changed.append({attribute: {"old": old_expense[attribute], "new": expense[attribute]}})

        key = self.ds_client.key("Expenses_Journal")
        entity = datastore.Entity(key=key)
        entity.update(
            {
                "Expenses_Id": old_expense.key.id,
                "Time": datetime.datetime.utcnow().isoformat(timespec="seconds")+'Z',
                "Attributes_Changed": json.dumps(changed),
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
                                        mail_body['mail_title'])
            msg_html = msg_html.replace('$MAIL_BODY',
                                        mail_body['mail_body'])

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

    def send_email_notification(self, mail_type, afas_data, expense_id):
        # Check if production project for sending emails
        if 'GOOGLE_CLOUD_PROJECT' in os.environ and \
                'vwt-p-' in os.environ['GOOGLE_CLOUD_PROJECT']:
            mail_body = None
            if mail_type == 'add_expense':
                mail_body = {
                    'from': config.GMAIL_SENDER_ADDRESS,
                    'reply_to': config.GMAIL_ADDEXPENSE_REPLYTO,
                    'subject': 'Er staat een nieuwe declaratie voor je klaar!',
                    'mail_title': 'Nieuwe declaratie',
                    'mail_body': """Beste {},<br /><br />
                    Er staat een nieuwe declaratie voor je klaar in de Declaratie-app, log in om deze te beoordelen.
                    Mochten er nog vragen zijn, mail gerust naar <a href="mailto:{}?subject=Declaratie-app%20%7C%20Nieuwe Declaratie">{}</a>.<br /><br />
                    Met vriendelijke groeten,<br />FSSC"""
                }

            if mail_body:
                if afas_data and 'Manager_personeelsnummer' in afas_data:
                    query = self.ds_client.query(kind='AFAS_HRM')
                    query.add_filter('Personeelsnummer', '=',
                                     afas_data['Manager_personeelsnummer'])
                    db_data = list(query.fetch(limit=1))

                    if db_data and len(db_data) > 0 and \
                            'email_address' in db_data[0]:
                        manager = db_data[0]
                        logging.info(f"Creating email for expense '{expense_id}'")

                        manager_naam = manager['Voornaam'] \
                            if 'Voornaam' in manager else 'ontvanger'

                        mail_body['mail_body'] = mail_body['mail_body'].format(
                            manager_naam, config.GMAIL_ADDEXPENSE_REPLYTO,
                            config.GMAIL_ADDEXPENSE_REPLYTO
                        )
                        self.send_message(expense_id, manager['email_address'],
                                          mail_body)
                    else:
                        logging.info(
                            "No manager found for employee '" +
                            afas_data['email_address'] + "', no email sent")
                else:
                    logging.info(
                        f"No employee data found for expense '{expense_id}'")
            else:
                logging.info(f"No mail body found for expense '{expense_id}'")
        else:
            logging.info("Dev mode active for sending e-mails")


class EmployeeExpenses(ClaimExpenses):
    def __init__(self, employee_id):
        super().__init__()
        self.employee_id = employee_id

    def _check_attachment_permission(self, expense):
        if expense["employee"]["email"] != self.employee_info["unique_name"]:
            return False
        else:
            return True

    def get_all_expenses(self):
        expenses_info = self._create_expenses_query()
        expenses_info.add_filter(
            "employee.afas_data.email_address", "=", self.employee_info["unique_name"]
        )
        return self._process_expenses_info(expenses_info)

    def _prepare_context_update_expense(self, data, expense):
        # Check if expense is from employee
        if not expense["employee"]["email"] == self.employee_info["unique_name"]:
            return {}, {}
        # Check if status is either rejected_by_manager or rejected_by_creditor
        if expense["status"]["text"] != "rejected_by_manager" and expense["status"]["text"] != "rejected_by_creditor":
            return {}, {}

        fields = {
            "status",
            "cost_type",
            "rnote",
            "note",
            "amount"
        }
        status = {
            "ready_for_manager",
            "ready_for_creditor",
            "cancelled",
        }
        return fields, status

    def _process_status_text_update(self, item, expense):
        if item == 'cancelled':
            expense["status"]["text"] = item
        else:
            if expense['status']['text'] in ['rejected_by_creditor', 'rejected_by_manager'] \
                    and item == 'ready_for_manager':
                self._process_status_amount_update(expense['amount'], expense)
            pass

    def _process_status_amount_update(self, amount, expense):
        # If amount is set when employee updates expense check what status it should be
        # If amount is less then 50 manager can be skipped
        if amount < 50:
            expense["status"]["text"] = "ready_for_creditor"
        else:
            expense["status"]["text"] = "ready_for_manager"

    def add_attachment(self, expense_id, data):
        expense_key = self.ds_client.key("Expenses", expense_id)
        expense = self.ds_client.get(expense_key)
        if not expense:
            return make_response(jsonify('Attempt to add attachment to undefined expense claim', 400))
        if expense["employee"]["email"] != self.employee_info["unique_name"]:
            return make_response(jsonify('Unauthorized'), 403)

        self.create_attachment(
            data,
            expense.key.id_or_name,
            self.employee_info["unique_name"]
        )

        return '', 204


class DepartmentExpenses(ClaimExpenses):
    def _check_attachment_permission(self, expense):
        return expense["employee"]["afas_data"]["Manager_personeelsnummer"] == self.get_manager_identifying_value()

    def __init__(self):
        super().__init__()

    def get_manager_identifying_value(self):
        afas_data = self.get_employee_afas_data(self.employee_info["unique_name"])
        if afas_data:
            return afas_data["Personeelsnummer"]
        else:
            return None

    def get_all_expenses(self):
        expenses_info = self._create_expenses_query()
        expenses_info.add_filter(
            "status.text",
            "=",
            "ready_for_manager"
        )
        expenses_info.add_filter(
            "employee.afas_data.Manager_personeelsnummer",
            "=",
            self.get_manager_identifying_value()
        )
        # expenses_data = expenses_info.fetch(limit=10)
        return self._process_expenses_info(expenses_info)

    def _prepare_context_update_expense(self, data, expense):
        # Check if requesting manager is manager of this employee
        if expense["employee"]["afas_data"]["Manager_personeelsnummer"] == self.get_manager_identifying_value():
            fields = {
                "status",
                "cost_type",
                "rnote"
            }
            status = {
                "ready_for_creditor",
                "rejected_by_manager",
            }
        else:
            fields = {}
            status = {}

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
        else:
            return make_response(jsonify(None), 204)

    def _prepare_context_update_expense(self, data, expense):
        fields = {
            "status",
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

            values = {
                'amount': {
                    'type': float,
                    'min_val': 0.00
                },
                'transaction_date': {
                    'type': str,
                    'date_format': '%Y-%m-%dT%H:%M:%S.%fZ',
                    'max_val': datetime.datetime.today() + datetime.timedelta(hours=2)
                }
            }
            if value_funnel(values, form_data.to_dict()):
                form_data.escape_characters()
                return expense_instance.add_expenses(form_data)
            else:
                return 'Some data is missing or incorrect', 400
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


def get_document(document_id, document_type):
    """
    Get a requested booking or payment file from a booking or payment identity in the format of
    1. Booking File => month_day_file_name => 7_12_12:34-12-07-2019
    2. Document File => month_day_file_name => 7_12_12:34-12-07-2019
    e.g => http://{HOST}/finances/expenses/documents/7_12_12:34-12-07-2019/kinds/payment_file
    :rtype: None
    :return"""

    expense_instance = ClaimExpenses()
    export_file = expense_instance.get_single_document_reference(document_id=document_id, document_type=document_type)
    # Separate Content

    if document_type == 'payment_file':
        content_response = {
            "content_type": "application/xml",
            "file": MD.parse(export_file.name).toprettyxml(encoding="utf-8").decode()
        }
    elif document_type == 'booking_file':
        with open(export_file.name, "r") as file_in:
            content_response = {
                "content_type": "text/csv",
                "file": file_in.read()
            }
            file_in.close()
    else:
        logger.error(f'Invalid document type requested [{document_type}]')
        return make_response(f'Invalid document type requested [{document_type}]', 400)

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
    expense_instance = DepartmentExpenses()
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
            return expense_instance.update_expenses(expenses_id, form_data, True)
    except Exception as er:
        logging.exception('Exception on add_expense')
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
            values = {
                'amount': {
                    'min_val': 0.00
                },
                'transaction_date': {
                    'type': str,
                    'date_format': '%Y-%m-%dT%H:%M:%S.%fZ',
                    'max_val': datetime.datetime.today() + datetime.timedelta(hours=2)
                },
                'status': {
                    'range': ['ready_for_manager', 'ready_for_creditor']
                }
            }

            if value_funnel(values, form_data):
                return expense_instance.update_expenses(expenses_id, form_data)
            else:
                return 'Some data is missing or incorrect', 400
    except Exception as er:
        logging.exception("Update exp")
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
            expense_instance = DepartmentExpenses()
            return expense_instance.update_expenses(expenses_id, form_data, True)
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


def get_attachment_finances_creditor(expenses_id):
    """
    Get attachment by expenses id
    :param expenses_id:
    :return:
    """
    expense_instance = ControllerExpenses()
    return expense_instance.get_attachment(expenses_id)


def get_attachment_finances_manager(expenses_id):
    expense_instance = DepartmentExpenses()
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
            values = {
                'content': {
                    'data_type_range': ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg']
                }
            }
            if value_funnel(values, form_data.to_dict()):
                return expense_instance.add_attachment(expenses_id, form_data)
            else:
                return 'Some data is missing or incorrect', 400
    except Exception as er:
        logging.exception('Exception on add_expense')
        return jsonify(er.args), 500


def api_base_url():
    base_url = request.host_url

    if 'GAE_INSTANCE' in os.environ:
        base_url = f"https://{os.environ['GOOGLE_CLOUD_PROJECT']}.appspot.com/"

    return base_url


def value_funnel(values, data):

    # TODO - Add to package
    for value in values:
        if data.get(value) is not None:
            correct_type = issubclass(values[value].get('type'),
                                      type(data[value])) if values[value].get('type') is not None else True
            in_range = data[value] in values[value].get('range') if values[value].get('range') is not None else True
            correct_data_type = re.search("(?<=data:).*?(?=;)",
                                          data[value])[0] in values[value].get('data_type_range') \
                if values[value].get('data_type_range') is not None else True
            date_format = True
            if values[value].get('date_format'):
                try:
                    data[value] = datetime.datetime.strptime(data[value], values[value].get('date_format'))
                    date_format = True
                except ValueError:
                    date_format = False
            min_val = values[value].get('min_val') < data[value] \
                if values[value].get('min_val') is not None and date_format else True
            max_val = values[value].get('max_val') > data[value] \
                if values[value].get('max_val') is not None and date_format else True
            if not (correct_type and min_val and max_val and date_format and in_range and correct_data_type):
                return False
    return True
