import base64
import copy
import csv
import datetime
import hashlib
import io
import json
import logging
import os
import re
import tempfile
import xml.etree.cElementTree as ET  # nosec
from abc import abstractmethod
from decimal import Decimal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO
from typing import Any, Dict

import config
import connexion
import dateutil
import defusedxml.minidom as MD
import firebase_admin
import google.auth
import googleapiclient.discovery
import pandas as pd
import pytz
import requests
import unidecode
from apiclient import errors
from defusedxml import defuse_stdlib
from firebase_admin import messaging as fb_messaging
from flask import Response, g, jsonify, make_response, request, send_file
from google.cloud import datastore, secretmanager_v1, storage
from openapi_server.auth import get_delegated_credentials
from openapi_server.controllers.businessrules_controller import \
    BusinessRulesEngine
from openapi_server.controllers.translate_responses import \
    make_response_translated
from openapi_server.models.attachment_data import AttachmentData
from openapi_server.models.employee_profile import \
    EmployeeProfile  # noqa: E501
from openapi_server.models.expense_data import ExpenseData
from OpenSSL import crypto
from pikepdf import Pdf

logger = logging.getLogger(__name__)
defuse_stdlib()

# Constants
EXPORTABLE_STATUSES = ["approved"]
VWT_TIME_ZONE = "Europe/Amsterdam"
FILTERED_OUT_ON_PROCESS = [
    "approved",
    "exported",
]

REJECTION_NOTES = {
    1: {
        "rnote_id": 1,
        "form": "static",
        "rnote": "Deze kosten kun je declareren via Regweb (PSA)",
        "translations": {
            "nl": "Deze kosten kun je declareren via Regweb (PSA)",
            "en": "These costs can be claimed via Regweb (PSA)",
            "de": "Diese Kosten können über Regweb (PSA) geltend gemacht werden",
        },
    },
    2: {
        "rnote_id": 2,
        "form": "static",
        "rnote": "Deze kosten kun je declareren via de leasemaatschappij",
        "translations": {
            "nl": "Deze kosten kun je declareren via de leasemaatschappij",
            "en": "These costs can be claimed via the lease company",
            "de": "Diese Kosten können über die Leasinggesellschaft geltend gemacht werden",
        },
    },
    3: {
        "rnote_id": 3,
        "form": "static",
        "rnote": "Deze kosten zijn al gedeclareerd",
        "translations": {
            "nl": "Deze kosten zijn al gedeclareerd",
            "en": "These costs have already been claimed",
            "de": "Diese Kosten würden bereits geltend gemacht",
        },
    },
    4: {
        "rnote_id": 4,
        "form": "dynamic",
        "rnote": "note",
        "translations": {
            "nl": "Andere reden:",
            "en": "Other reason:",
            "de": "Anderer Grund:",
        },
    },
}


class ClaimExpenses:
    """
    Class based function to house all Expenses functionality

    """

    def __init__(self):
        if len(firebase_admin._apps) <= 0:
            self.fb_app = firebase_admin.initialize_app()  # Firebase
        else:
            self.fb_app = firebase_admin.get_app()  # Firebase

        self.ds_client = datastore.Client()  # Datastore
        self.cs_client = storage.Client()  # CloudStores
        self.employee_info = g.token
        self.bucket_name = config.GOOGLE_STORAGE_BUCKET

    def get_employee_afas_data(self, unique_name):
        """
        Data Access Link to the AFAS environment to retrieve employee information
        - Bank Account
        - Company Code
        - Any other detail we will be needing to complete the payment
        This link is made available through the HR-On boarding project
        :param unique_name: An email address
        """
        # Fake AFAS data for E2E:
        if unique_name == "opensource.e2e@vwtelecom.com":
            return config.e2e_afas_data

        try:
            unique_name = str(unique_name).lower().strip()
        except Exception:
            logging.error(
                f"Could not transform unique name '{unique_name}' to lowercase"
            )
        else:
            employees = self._query_afas_employee_on_field("upn", unique_name)

            # NOTE: this is a temporary fallback query for Recognize accounts (DAT-7510)
            if not employees:
                employees = self._query_afas_employee_on_field("email_address", unique_name)

            if employees and len(employees) == 1:
                return dict(employees[0].items())

            logging.warning(f"No detail of {unique_name} found in HRM -AFAS")
        return None

    def _query_afas_employee_on_field(self, field: str, value, limit: int = 1) -> list:
        """
        Returns a list of all employees that match the 'equals' query.

        :param field: name of the database field to check.
        :type field: str
        :param value: passing value of the field in the database.
        :type value: any
        :param limit: limit on returned employees

        :return: a list of all employees that match the 'equals' query.
        :rtype: list
        """
        query = self.ds_client.query(kind="AFAS_HRM")
        query.add_filter(field, "=", value)
        return list(query.fetch(limit=limit))

    def create_attachment(self, attachment, expenses_id, email):
        """Creates an attachment"""
        today = pytz.UTC.localize(datetime.datetime.now())
        email_name = email.split("@")[0]
        filename = (
            f"{today.hour:02d}:{today.minute:02d}:{today.second:02d}-{today.year}{today.month}{today.day}"
            f"-{attachment.name}"
        )
        bucket = self.cs_client.get_bucket(self.bucket_name)
        blob = bucket.blob(f"exports/attachments/{email_name}/{expenses_id}/{filename}")

        try:
            if "," not in attachment.content:
                return False
            content_type = re.search(
                r"(?<=^data:)(.*)(?=;base64)", attachment.content.split(",")[0]
            )
            content = base64.b64decode(
                attachment.content.split(",")[1]
            )  # Set the content from base64
            if not content_type or not content:
                return False
            content_type = content_type.group()
            if content_type == "application/pdf":
                # If a PDF is uploaded, we will process it first
                # by flattening its annotations (e.g. images, links, videos, etc.).
                pdf = Pdf.open(
                    io.BytesIO(content)
                )  # Creating PDF representation from content bytes.
                pdf.flatten_annotations()  # Flattening annotations.

                pdf_stream = io.BytesIO()  # Create a new stream to save the data to.
                pdf.save(pdf_stream)  # Save the PDF to the new stream.

                pdf_stream.seek(0)  # Reset stream index so we can read from start.
                content = pdf_stream.read()  # Read stream.

                pdf_stream.close()
                pdf.close()

            blob.upload_from_string(
                content,  # Upload content (can be decoded b64 from request or read data from temp flat file)
                content_type=content_type,
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

        if not expense:
            return make_response_translated("Declaratie niet gevonden", 404)
        if expense["employee"]["email"] != self.employee_info["unique_name"]:
            return make_response_translated("Geen overeenkomst op e-mail", 403)

        bucket = self.cs_client.get_bucket(self.bucket_name)
        blob = bucket.blob(
            f"exports/attachments/{email_name}/{expenses_id}/{attachments_name}"
        )

        blob.delete()

        return make_response("", 204)

    def get_cost_types(self):
        """
        Get cost types from a CSV file
        :return:
        """

        cost_types = self.ds_client.query(kind="CostTypes").fetch()

        if cost_types:
            results = [
                {
                    "ctype": row.get("Omschrijving", ""),
                    "cid": row.key.name,
                    "active": row.get("Active", ""),
                    "description": row.get(
                        "Description",
                        {
                            "nl": row.get("Omschrijving", row.key.name),
                            "en": row.get("Omschrijving", row.key.name),
                            "de": row.get("Omschrijving", row.key.name),
                        },
                    ),
                    "managertype": row.get("ManagerType", "linemanager"),
                    "message": row.get("Message", {}),
                }
                for row in cost_types
            ]
            return jsonify(results)

        return make_response("", 204)

    def get_manager_identifying_value(self):
        afas_data = self.get_employee_afas_data(self.employee_info["unique_name"])
        if afas_data:
            return afas_data["Personeelsnummer"]

        return None

    def get_expenses(self, expenses_id, permission):
        """
        Get single expense by expense id and check if permission is employee if expense is from employee
        :param expenses_id:
        :param permission:
        :return:
        """
        manager_number = (
            int(self.get_manager_identifying_value())
            if permission == "manager"
            else None
        )

        with self.ds_client.transaction(read_only=True):
            exp_key = self.ds_client.key("Expenses", expenses_id)
            expense = self.ds_client.get(exp_key)

            if not expense:
                return make_response_translated("Declaratie niet gevonden", 404)

            cost_type_entity, cost_type_active = self._process_cost_type(
                expense["cost_type"]
            )
            cost_type = None if cost_type_entity is None else cost_type_entity.key.name

            if permission == "employee":
                if (
                    not expense["employee"]["email"]
                    == self.employee_info["unique_name"]
                ):
                    return make_response_translated("Geen overeenkomst op e-mail", 403)
            elif permission == "manager":
                if expense.get(
                    "manager_type", "linemanager"
                ) == "leasecoordinator" and "leasecoordinator.write" not in self.employee_info.get(
                    "scopes", []
                ):
                    return make_response_translated(
                        "Geen overeenkomst op leasecoordinator", 403
                    )
                elif (
                    expense.get("manager_type", "linemanager") != "leasecoordinator"
                    and not expense["employee"]["afas_data"]["Manager_personeelsnummer"]
                    == manager_number
                ):
                    return make_response_translated(
                        "Geen overeenkomst op manager e-email", 403
                    )

            return jsonify(
                {
                    "id": str(expense.id),
                    "amount": expense["amount"],
                    "note": expense["note"],
                    "cost_type": cost_type,
                    "claim_date": expense["claim_date"],
                    "transaction_date": expense["transaction_date"],
                    "employee": expense["employee"]["full_name"],
                    "status": expense["status"],
                    "flags": expense.get("flags", {}),
                }
            )

    @abstractmethod
    def _check_attachment_permission(self, expense):
        pass

    def get_attachment(self, expenses_id):
        """Get attachments with expenses_id"""
        with self.ds_client.transaction(read_only=True):
            exp_key = self.ds_client.key("Expenses", expenses_id)
            expense = self.ds_client.get(exp_key)

        if not expense:
            return make_response_translated("Declaratie niet gevonden", 404)
        if not self._check_attachment_permission(expense):
            return make_response_translated("Ongeautoriseerd", 403)

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
                "content": stream_read.decode("utf-8"),
                "name": blob.name.split("/")[-1],
            }
            results.append(content_result)

        return jsonify(results)

    @abstractmethod
    def get_all_expenses(self):
        pass

    @staticmethod
    def _merge_rejection_note(status):
        if "rnote" in status and "rnote_id" not in status:
            for key in REJECTION_NOTES:
                if REJECTION_NOTES[key]["rnote"] == status["rnote"]:
                    status["rnote_id"] = REJECTION_NOTES[key]["rnote_id"]

            if "rnote_id" not in status:
                status["rnote_id"] = 4

        return status

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
                    BusinessRulesEngine().employed_rule(afas_data)
                    BusinessRulesEngine().pao_rule(data, afas_data)

                    if not afas_data.get("IBAN"):
                        return make_response_translated(
                            "Uw bankrekeningnummer (IBAN) is niet bekend in de personeelsadministratie",
                            403,
                        )
                    if not afas_data.get("Manager_personeelsnummer"):
                        return make_response_translated(
                            "Manager nummer niet bekend in de personeelsadministratie",
                            403,
                        )

                    cost_type_entity, cost_type_active = self._process_cost_type(
                        data.cost_type
                    )
                    if cost_type_entity is None or not cost_type_active:
                        return make_response_translated("Geen geldige kostensoort", 400)
                    data.manager_type = cost_type_entity.get(
                        "ManagerType", "linemanager"
                    )

                except ValueError as exception:
                    return make_response_translated(str(exception), 400)
                else:
                    key = self.ds_client.key("Expenses")
                    entity = datastore.Entity(key=key)
                    try:
                        new_expense = {
                            "employee": dict(
                                afas_data=afas_data,
                                email=self.employee_info["unique_name"],
                                family_name=self.employee_info.get("family_name"),
                                given_name=self.employee_info.get("given_name"),
                                full_name=self.employee_info["name"],
                            ),
                            "amount": data.amount,
                            "note": data.note,
                            "cost_type": cost_type_entity.key.name,
                            "transaction_date": data.transaction_date,
                            "claim_date": datetime.datetime.utcnow().isoformat(
                                timespec="seconds"
                            )
                            + "Z",
                            "status": dict(export_date="never", text=ready_text),
                            "manager_type": data.manager_type,
                        }
                    except KeyError:
                        return make_response_translated("Er ging iets fout", 400)

                    response = {}

                    modified_data = (
                        BusinessRulesEngine().to_dict(data)
                        if isinstance(data, ExpenseData)
                        else data
                    )
                    BusinessRulesEngine().duplicate_rule(modified_data, afas_data)
                    if "flags" in modified_data:
                        new_expense["flags"] = modified_data["flags"]
                        response["flags"] = modified_data["flags"]

                    entity.update(new_expense)
                    self.ds_client.put(entity)
                    self.expense_journal({}, entity)

                    response["id"] = entity.key.id_or_name

                    return make_response(jsonify(response), 201)
            else:
                return make_response_translated(
                    "Medewerker niet bekend in de personeelsadministratie", 403
                )
        else:
            return make_response_translated(
                "Unieke identificatie niet in token gevonden", 403
            )

    def _process_status_text_update(self, data, expense):
        if (
            expense["status"]["text"] in ["rejected_by_creditor", "rejected_by_manager"]
            and data["status"] == "ready_for_manager"
        ):
            expense["status"]["text"] = self._determine_status_amount_update(
                expense["amount"], data
            )
        else:
            expense["status"]["text"] = data["status"]

    def _determine_status_amount_update(self, amount, data):
        min_amount = data["min_amount"]
        manager_type = data["manager_type"]

        return (
            "ready_for_creditor"
            if min_amount > 0
            and amount < min_amount
            and manager_type != "leasecoordinator"
            else data["status"]
        )

    @abstractmethod
    def _prepare_context_update_expense(self, expense):
        pass

    def _prepare_response_update_expense(self, expense):
        return {
            "id": expense.id,
            "amount": expense["amount"],
            "note": expense["note"],
            "cost_type": expense["cost_type"],
            "claim_date": expense["claim_date"],
            "transaction_date": expense["transaction_date"],
            "employee": expense["employee"]["full_name"],
            "status": expense["status"],
            "flags": expense.get("flags", {}),
        }

    def update_expenses(self, expenses_id, data, note_check=False):
        """
        Change the status and add note from expense
        :param expenses_id:
        :param data:
        :param note_check:
        :return:
        """
        if note_check:
            if not data.get("rnote_id") and (
                data.get("status") == "rejected_by_manager"
                or data.get("status") == "rejected_by_creditor"
            ):
                return make_response_translated(
                    "Sommige gegevens ontbraken of waren onjuist", 400
                )

        with self.ds_client.transaction():
            exp_key = self.ds_client.key("Expenses", expenses_id)
            expense = self.ds_client.get(exp_key)
            old_expense = copy.deepcopy(expense)

            if not expense:
                return make_response_translated("Declaratie niet gevonden", 404)

            # Check validity cost-type
            cost_type_entity, cost_type_active = self._process_cost_type(
                data.get("cost_type", expense["cost_type"])
            )
            if "cost_type" in data:
                if cost_type_entity is None or not cost_type_active:
                    return make_response_translated("Geen geldige kostensoort", 400)
                data["cost_type"] = cost_type_entity.key.name

            if (
                expense["status"]["text"] == "draft"
                or "rejected" in expense["status"]["text"]
            ) and "ready" in data.get("status", ""):

                if len(data) > 1:
                    return make_response_translated(
                        "Het indienen van een declaratie is niet toegestaan tijdens het aanpassen van velden",
                        403,
                    )

                data["min_amount"] = cost_type_entity.get("MinAmount", 50)
                if data["min_amount"] == 0 or data["min_amount"] <= data.get(
                    "amount", expense["amount"]
                ):
                    data["status"] = "ready_for_manager"
                else:
                    data["status"] = "ready_for_creditor"

            allowed_fields, allowed_statuses = self._prepare_context_update_expense(
                expense
            )
            if not allowed_fields or not allowed_statuses:
                return make_response_translated(
                    "De inhoud van deze methode is niet geldig", 403
                )

            try:
                BusinessRulesEngine().employed_rule(expense["employee"]["afas_data"])
                BusinessRulesEngine().pao_rule(data, expense["employee"]["afas_data"])
                data["manager_type"] = cost_type_entity.get(
                    "ManagerType", "linemanager"
                )
            except ValueError as exception:
                return make_response_translated(str(exception), 400)

            if not self._has_attachments(expense, data):
                return make_response_translated(
                    "De declaratie moet minimaal één bijlage hebben", 403
                )

            if "rnote_id" in data:
                rnote_id, rnote = self._process_rejection_note(
                    data.get("rnote_id"), data.get("rnote")
                )
                if not rnote_id or not rnote:
                    return make_response_translated("Geen geldige afwijzing", 400)
                data["rnote_id"] = rnote_id
                data["rnote"] = rnote

            BusinessRulesEngine().duplicate_rule(
                data, expense["employee"]["afas_data"], expense
            )
            # If there are no warnings to display: remove flags property from entity
            if "flags" not in data and "flags" in expense:
                del expense["flags"]

            valid_update = self._update_expenses(
                data, allowed_fields, allowed_statuses, expense
            )
            if not valid_update:
                return make_response_translated(
                    "De inhoud van deze methode is niet geldig", 403
                )

            self.expense_journal(old_expense, expense)

        if data["status"] in [
            "rejected_by_manager",
            "rejected_by_creditor",
        ] and old_expense["status"]["text"] in [
            "ready_for_manager",
            "ready_for_creditor",
        ]:
            self.send_notification(
                "rejected_expense",
                expense["employee"]["afas_data"],
                expense.key.id_or_name,
                data.get("manager_type", "linemanager"),
            )
        elif data["status"] == "ready_for_manager" and old_expense["status"][
            "text"
        ] in ["draft", "rejected_by_manager", "rejected_by_creditor"]:
            self.send_notification(
                "assess_expense",
                expense["employee"]["afas_data"],
                expense.key.id_or_name,
                data.get("manager_type", "linemanager"),
            )

        return make_response(
            jsonify(self._prepare_response_update_expense(expense)), 200
        )

    def _update_expenses(self, data, allowed_fields, allowed_statuses, expense):
        items_to_update = list(allowed_fields.intersection(set(data.keys())))
        need_to_save = False
        for item in items_to_update:
            if item == "rnote":
                need_to_save = True
                expense["status"]["rnote"] = data[item]
            elif item == "rnote_id":
                need_to_save = True
                expense["status"]["rnote_id"] = data[item]
            elif item != "status" and expense.get(item, None) != data[item]:
                need_to_save = True
                expense[item] = data[item]

        if "status" in items_to_update:
            logger.debug(
                f"Employee status to update [{data['status']}] old [{expense['status']['text']}], legal "
                f"transition [{allowed_statuses}]"
            )
            if data["status"] in allowed_statuses:
                need_to_save = True
                self._process_status_text_update(data, expense)
            else:
                logging.info(
                    "Rejected unauthorized status transition for "
                    + f"{expense.key.id_or_name}: {expense['status']['text']} "
                    + f"> {data['status']}"
                )
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

    def _has_attachments(self, expense, data):
        allowed_statuses_new = [
            "draft",
            "cancelled",
            "rejected_by_manager",
            "rejected_by_creditor",
        ]
        allowed_statuses_old = ["rejected_by_manager", "rejected_by_creditor"]
        if (
            data.get("status", "") in allowed_statuses_new
            or expense["status"]["text"] in allowed_statuses_old
        ):
            return True

        email_name = expense["employee"]["email"].split("@")[0]

        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)
        blobs = expenses_bucket.list_blobs(
            prefix=f"exports/attachments/{email_name}/{str(expense.key.id)}"
        )

        return True if len(list(blobs)) > 0 else False

    @staticmethod
    def _process_rejection_note(rnote_id, rnote=None):
        if (rnote and not rnote_id) or not REJECTION_NOTES.get(rnote_id, None):
            return False, False

        rejection = REJECTION_NOTES.get(rnote_id)

        if rejection["form"] == "dynamic" and not rnote:
            return False, False
        elif rejection["form"] != "dynamic":
            rnote = rejection["rnote"]

        return rnote_id, rnote

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
            bic = next(
                (r["bic"] for r in bank_data if r["identifier"] == bank_code), None
            )
        else:
            bic = None

        if bic:
            return bic

        return "NOTPROVIDED"  # Bank will determine the BIC based on the Debtor Account

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
            return make_response_translated("Geen exports beschikbaar", 204)

        now = datetime.datetime.utcnow()

        local_tz = pytz.timezone(VWT_TIME_ZONE)
        local_now = now.replace(tzinfo=pytz.utc).astimezone(local_tz)

        export_file_name = now.strftime("%Y%m%d%H%M%S")

        result_bk = self.create_booking_file(
            expense_claims_to_export, export_file_name, local_now
        )
        result_pm = self.create_payment_file(
            expense_claims_to_export, export_file_name, local_now
        )

        if not result_bk[0] and result_pm[0]:
            logging.error("Could not upload booking file")
            return make_response_translated("Kan boekingsdossier niet uploaden", 400)
        if result_bk[0] and not result_pm[0]:
            logging.error("Could not upload payment file")
            return make_response_translated("Kan betalingsbestand niet uploaden", 400)
        if not result_bk[0] and not result_pm[0]:
            logging.error("Could not upload booking and payment file")
            return make_response_translated(
                "Kan boekingsdossier en betalingsbestand niet uploaden", 400
            )

        retval = {
            "file_list": [
                {
                    "booking_file": f"{api_base_url()}finances/expenses/documents/{export_file_name}/kinds/booking_file",
                    "payment_file": f"{api_base_url()}finances/expenses/documents/{export_file_name}/kinds/payment_file",
                    "export_date": now.isoformat(timespec="seconds") + "Z",
                }
            ]
        }

        self.update_exported_expenses(expense_claims_to_export, now)

        return make_response(jsonify(retval), 200)

    def create_booking_file(
        self, expense_claims_to_export, export_filename, document_date
    ):
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

            trans_date = dateutil.parser.parse(
                expense_detail["transaction_date"]
            ).strftime("%d-%m-%Y")

            boekingsomschrijving_bron = f"{expense_detail['employee']['afas_data']['Personeelsnummer']} {trans_date}"

            expense_detail["boekingsomschrijving_bron"] = boekingsomschrijving_bron

            grootboek_number = expense_detail["cost_type"]
            cost_type_split = (
                grootboek_number.split(":")[1]
                if ":" in grootboek_number
                else grootboek_number
            )

            try:
                key = self.ds_client.key("CostTypes", cost_type_split)
                cost_entity = self.ds_client.get(key=key)
                grootboek_number = cost_entity["Grootboek"]
            except Exception:
                logging.warning("Old cost_type")
                grootboek_number = cost_type_split

            booking_file_data.append(
                {
                    "BoekingsomschrijvingBron": boekingsomschrijving_bron,
                    "Document-datum": document_date.strftime("%d%m%Y"),
                    "Boekings-jaar": document_date.strftime("%Y"),
                    "Periode": document_date.strftime("%m"),
                    "Bron-bedrijfs-nummer": config.BOOKING_FILE_STATICS[
                        "Bron-bedrijfs-nummer"
                    ],
                    "Bron gr boekrek": config.BOOKING_FILE_STATICS[
                        "Bron-grootboek-rekening"
                    ],
                    "Bron Org Code": config.BOOKING_FILE_STATICS["Bron-org-code"],
                    "Bron Process": "000",
                    "Bron Produkt": "000",
                    "Bron EC": "000",
                    "Bron VP": "00",
                    "Doel-bedrijfs-nummer": config.BOOKING_FILE_STATICS[
                        "Doel-bedrijfs-nummer"
                    ],
                    "Doel-gr boekrek": grootboek_number,
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
        return unidecode.unidecode(expense["employee"]["afas_data"].get("Naam"))

    def create_payment_file(
        self, expense_claims_to_export, export_filename, document_time
    ):

        """
        Creates an XML file from claim expenses that have been exported. Thus a claim must have a status
        ==> status -- 'booking-file-created'
        """
        booking_timestamp_id = document_time.strftime("%Y%m%d%H%M%S")

        message_id = f"200/DEC/{booking_timestamp_id}"
        payment_info_id = f"200/DEC/{booking_timestamp_id}"

        # Set namespaces
        ET.register_namespace("", "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03")
        root = ET.Element("{urn:iso:std:iso:20022:tech:xsd:pain.001.001.03}Document")

        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")

        customer_header = ET.SubElement(root, "CstmrCdtTrfInitn")

        ctrl_sum = Decimal(0)
        for expense in expense_claims_to_export:
            ctrl_sum += Decimal(str(expense["amount"]))

        # Group Header
        header = ET.SubElement(customer_header, "GrpHdr")
        ET.SubElement(header, "MsgId").text = message_id
        ET.SubElement(header, "CreDtTm").text = document_time.isoformat(
            timespec="seconds"
        )
        ET.SubElement(header, "NbOfTxs").text = str(
            len(expense_claims_to_export)  # Number Of Transactions in the batch
        )
        ET.SubElement(header, "CtrlSum").text = str(
            ctrl_sum
        )  # Total amount of the batch
        initiating_party = ET.SubElement(header, "InitgPty")
        ET.SubElement(initiating_party, "Nm").text = config.OWN_ACCOUNT["bedrijf"]

        #  Payment Information
        payment_info = ET.SubElement(customer_header, "PmtInf")
        ET.SubElement(payment_info, "PmtInfId").text = message_id
        ET.SubElement(payment_info, "PmtMtd").text = "TRF"  # Standard Value
        ET.SubElement(payment_info, "NbOfTxs").text = str(
            len(expense_claims_to_export)  # Number Of Transactions in the batch
        )
        ET.SubElement(payment_info, "CtrlSum").text = str(
            ctrl_sum
        )  # Total amount of the batch

        # Payment Type Information
        payment_typ_info = ET.SubElement(payment_info, "PmtTpInf")
        ET.SubElement(payment_typ_info, "InstrPrty").text = "NORM"
        payment_tp_service_level = ET.SubElement(payment_typ_info, "SvcLvl")
        ET.SubElement(payment_tp_service_level, "Cd").text = "SEPA"

        ET.SubElement(
            payment_info, "ReqdExctnDt"
        ).text = document_time.date().isoformat()

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
        payment_debitor_agent_id = ET.SubElement(payment_debitor_agent, "FinInstnId")
        ET.SubElement(payment_debitor_agent_id, "BIC").text = config.OWN_ACCOUNT["bic"]
        for expense in expense_claims_to_export:
            # Transaction Transfer Information
            transfer = ET.SubElement(payment_info, "CdtTrfTxInf")
            transfer_payment_id = ET.SubElement(transfer, "PmtId")
            ET.SubElement(transfer_payment_id, "InstrId").text = payment_info_id
            ET.SubElement(transfer_payment_id, "EndToEndId").text = expense[
                "boekingsomschrijving_bron"
            ]

            # Amount
            amount = ET.SubElement(transfer, "Amt")
            ET.SubElement(amount, "InstdAmt", Ccy="EUR").text = str(expense["amount"])
            ET.SubElement(transfer, "ChrgBr").text = "SLEV"

            iban = expense["employee"]["afas_data"].get("IBAN")
            if not iban:
                iban = ""

            # Creditor Agent Tag Information
            amount_agent = ET.SubElement(transfer, "CdtrAgt")
            payment_creditor_agent_id = ET.SubElement(amount_agent, "FinInstnId")
            ET.SubElement(
                payment_creditor_agent_id, "BIC"
            ).text = self.get_iban_details(iban)

            # Creditor name
            creditor_name = ET.SubElement(transfer, "Cdtr")
            ET.SubElement(creditor_name, "Nm").text = self._gather_creditor_name(
                expense
            )

            # Creditor Account
            creditor_account = ET.SubElement(transfer, "CdtrAcct")
            creditor_account_id = ET.SubElement(creditor_account, "Id")

            # <ValidationPass> on whitespaces
            ET.SubElement(creditor_account_id, "IBAN").text = iban.replace(" ", "")

            # Remittance Information
            remittance_info = ET.SubElement(transfer, "RmtInf")
            ET.SubElement(remittance_info, "Ustrd").text = expense[
                "boekingsomschrijving_bron"
            ]

        payment_xml_string = ET.tostring(root, encoding="utf8", method="xml")

        # Save File to CloudStorage
        bucket = self.cs_client.get_bucket(self.bucket_name)
        blob = bucket.blob(
            f"exports/payment_file/{document_time.year}/{document_time.month}/{document_time.day}/{export_filename}"
        )
        blob.upload_from_string(payment_xml_string, content_type="application/xml")

        payment_file = MD.parseString(payment_xml_string).toprettyxml(encoding="utf-8")

        if (
            config.POWER2PAY_URL
            and config.POWER2PAY_AUTH_USER
            and config.POWER2PAY_AUTH_PASSWORD
        ):
            if not self.send_to_power2pay(payment_xml_string):
                return False, None, jsonify({"Info": "Failed to upload payment file"})

            logger.info("Power2Pay upload successful")
        else:
            logger.warning("Sending to Power2Pay is disabled")

        return True, export_filename, payment_file

    def get_secret(self, project_id, secret_id):

        client = secretmanager_v1.SecretManagerServiceClient()

        secret_name = client.secret_version_path(project_id, secret_id, "latest")

        response = client.access_secret_version(request={"name": secret_name})
        payload = response.payload.data.decode("UTF-8")

        return payload

    def make_temp(self, str):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as temp_file:
            temp_file.write(str)

        return temp_file.name

    def get_certificates(self):

        passphrase = self.get_secret(
            os.environ["GOOGLE_CLOUD_PROJECT"], config.PASSPHRASE
        )
        key = self.get_secret(os.environ["GOOGLE_CLOUD_PROJECT"], config.KEY)
        certificate = self.get_secret(
            os.environ["GOOGLE_CLOUD_PROJECT"], config.CERTIFICATE
        )

        pk = crypto.load_privatekey(crypto.FILETYPE_PEM, key, passphrase.encode())

        key_file = self.make_temp(
            str(
                crypto.dump_privatekey(
                    crypto.FILETYPE_PEM, pk, cipher=None, passphrase=None
                ),
                "utf-8",
            )
        )

        cert_file = self.make_temp(certificate)

        return (cert_file, key_file)

    def send_to_power2pay(self, payment_xml_string):

        cert = self.get_certificates()
        auth_password = self.get_secret(
            os.environ["GOOGLE_CLOUD_PROJECT"], config.POWER2PAY_AUTH_PASSWORD
        )
        r = requests.post(
            config.POWER2PAY_URL,
            data=payment_xml_string,
            cert=cert,
            verify=True,
            auth=(config.POWER2PAY_AUTH_USER, auth_password),
        )

        logger.info(f"Power2Pay send result {r.status_code}: {r.content}")

        return r.ok

    def get_all_documents_list(self):
        expenses_bucket = self.cs_client.get_bucket(self.bucket_name)

        all_exports_files = {"file_list": []}
        blobs = expenses_bucket.list_blobs(prefix=f"exports/booking_file")

        for blob in blobs:
            name = blob.name.split("/")[-1]

            all_exports_files["file_list"].append(
                {
                    "export_date": datetime.datetime.strptime(name, "%Y%m%d%H%M%S"),
                    "booking_file": f"{api_base_url()}finances/expenses/documents/{name}/kinds/booking_file",
                    "payment_file": f"{api_base_url()}finances/expenses/documents/{name}/kinds/payment_file",
                }
            )

        all_exports_files["file_list"] = sorted(
            all_exports_files["file_list"], key=lambda k: k["export_date"], reverse=True
        )
        return all_exports_files

    def get_single_document_reference(self, document_id, document_type):
        document_date = datetime.datetime.strptime(document_id, "%Y%m%d%H%M%S")
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

    def _process_cost_type(self, cost_type, cost_type_list=None):
        cost_type_split = cost_type.split(":")
        cost_type_id = cost_type

        if len(cost_type_split) == 2:
            cost_type_id = cost_type_split[1]

        if cost_type_list is None:
            key = self.ds_client.key("CostTypes", cost_type_id)
            cost_type_entity = self.ds_client.get(key=key)
        else:
            for ct in cost_type_list:
                if ct.key.name == cost_type_id:
                    cost_type_entity = ct
                    break

        cost_type_active = False
        if cost_type_entity is not None:
            cost_type_active = cost_type_entity.get("Active", False)

        return cost_type_entity, cost_type_active

    def _process_expenses_info(self, expenses_info):
        expenses_data = expenses_info.fetch()
        if expenses_data:
            cost_type_list = list(self.ds_client.query(kind="CostTypes").fetch())

            expenses_list = []
            for ed in expenses_data:

                cost_type_entity, cost_type_active = self._process_cost_type(
                    ed["cost_type"], cost_type_list
                )
                cost_type = (
                    None if cost_type_entity is None else cost_type_entity.key.name
                )

                expenses_list.append(
                    {
                        "id": ed.id,
                        "amount": ed["amount"],
                        "note": ed["note"],
                        "cost_type": cost_type,
                        "claim_date": ed["claim_date"],
                        "transaction_date": ed["transaction_date"],
                        "employee": ed["employee"]["full_name"],
                        "status": self._merge_rejection_note(ed["status"]),
                        "flags": ed.get("flags", {}),
                    }
                )

            return jsonify(expenses_list)
        return make_response("", 204)

    def expense_journal(self, old_expense, expense):
        changed = []

        def default(o):
            if isinstance(o, (datetime.date, datetime.datetime)):
                return o.isoformat(timespec="seconds") + "Z"

        for attribute in list(set(old_expense) | set(expense)):
            if attribute not in old_expense:
                changed.append({attribute: {"new": expense[attribute]}})
            elif attribute not in expense:
                changed.append(
                    {attribute: {"old": old_expense[attribute], "new": None}}
                )
            elif old_expense[attribute] != expense[attribute]:
                changed.append(
                    {
                        attribute: {
                            "old": old_expense[attribute],
                            "new": expense[attribute],
                        }
                    }
                )

        key = self.ds_client.key("Expenses_Journal")
        entity = datastore.Entity(key=key)
        entity.update(
            {
                "Expenses_Id": expense.key.id,
                "Time": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "Attributes_Changed": json.dumps(changed, default=default),
                "User": self.employee_info["unique_name"],
            }
        )
        self.ds_client.put(entity)

    def get_employee_locale(self, unique_name):
        locale_list = ["nl", "en", "de"]
        key = self.ds_client.key("EmployeeProfiles", unique_name)
        emp_profile = self.ds_client.get(key)

        if (
            emp_profile
            and "locale" in emp_profile
            and emp_profile["locale"] in locale_list
        ):
            return emp_profile["locale"]

        return "nl"

    def get_employee_push_token(self, unique_name):
        query = self.ds_client.query(kind="PushTokens")
        query.add_filter("unique_name", "=", unique_name)
        query.add_filter("push_token", ">", "")

        return list(query.fetch())

    def send_push_notification(self, mail_body, afas_data, expense_id, locale):
        upn = afas_data["upn"].strip()
        push_tokens = self.get_employee_push_token(upn)

        if push_tokens:
            active_push_tokens = []

            for token in push_tokens:
                if "push_token" in token:
                    active_push_tokens.append(token["push_token"])

            if len(active_push_tokens) > 0:
                # Set notification data
                notification_data = {
                    "username": str(upn),
                    "expense_id": str(expense_id),
                }

                # Create Android message
                android_notification = fb_messaging.AndroidNotification(
                    title=mail_body["title"][locale],
                    body=mail_body["body"][locale],
                    click_action="FCM_PLUGIN_ACTIVITY",
                )
                android_config = fb_messaging.AndroidConfig(
                    priority="normal", notification=android_notification
                )

                # Create ios message
                ios_notification = fb_messaging.Notification(
                    title=mail_body["title"][locale], body=mail_body["body"][locale]
                )

                # Merge multicast message
                multicast_message = fb_messaging.MulticastMessage(
                    tokens=active_push_tokens,
                    data=notification_data,
                    notification=ios_notification,
                    android=android_config,
                )

                try:
                    # Send multicast message
                    multicast_batch = fb_messaging.send_multicast(multicast_message)
                    logging.info(
                        "Push message batch: {} success(es) and {} failure(s) [{}]".format(
                            multicast_batch.success_count,
                            multicast_batch.failure_count,
                            expense_id,
                        )
                    )

                    for response in multicast_batch.responses:
                        if not response.success:
                            logging.info(
                                "Push message '{}' trows exception: {}".format(
                                    response.message_id, str(response.exception)
                                )
                            )
                except Exception as exception:
                    logging.info(
                        "Something went wrong while sending the push message batch for expense '{}': {}".format(
                            expense_id, str(exception)
                        )
                    )
                    return False

                return True

        logging.debug("No push token(s) found")
        return False

    def generate_mail(self, to, mail_body, locale):
        msg = MIMEMultipart("alternative")
        msg["From"] = config.GMAIL_SENDER_ADDRESS
        msg["Subject"] = mail_body["title"][locale]
        msg["Reply-To"] = config.GMAIL_ADDEXPENSE_REPLYTO
        msg["To"] = to

        with open("gmail_template.html", "r") as mail_template:
            msg_html = mail_template.read()

        msg_html = msg_html.replace("$MAIL_TITLE", mail_body["title"][locale])
        msg_html = msg_html.replace("$MAIL_SALUTATION", mail_body["salutation"][locale])
        msg_html = msg_html.replace("$MAIL_BODY", mail_body["body"][locale])
        msg_html = msg_html.replace("$MAIL_FOOTER", mail_body["footer"][locale])

        msg.attach(MIMEText(msg_html, "html"))
        raw = base64.urlsafe_b64encode(msg.as_bytes())
        raw = raw.decode()

        return {"raw": raw}

    def send_mail_notification(self, mail_body, afas_data, expense_id, locale):
        if (
            hasattr(config, "GMAIL_STATUS")
            and config.GMAIL_STATUS
            and (
                "GAE_INSTANCE" in os.environ
                or "GOOGLE_APPLICATION_CREDENTIALS" in os.environ
            )
        ):
            gmail_service = initialise_gmail_service(
                subject=config.GMAIL_SUBJECT_ADDRESS,
                scopes=["https://www.googleapis.com/auth/gmail.send"],
            )
            if gmail_service:
                try:
                    logging.info(f"Creating email for expense '{expense_id}'")
                    recipient_name = (
                        afas_data["Voornaam"]
                        if "Voornaam" in afas_data
                        else "ontvanger"
                    )

                    mail_body_feedback = {
                        "nl": """Mochten er nog vragen zijn, mail gerust naar""",
                        "en": """If you have any questions, feel free to mail to""",
                        "de": """Wenn Sie Fragen haben, senden Sie uns bitte eine E-Mail an""",
                    }
                    mail_body["salutation"] = {
                        "nl": "Beste {},",
                        "en": "Dear {},",
                        "de": "Lieber {},",
                    }
                    mail_body["footer"] = {
                        "nl": "Met vriendelijke groeten,<br />FSSC",
                        "en": "Kind regards,<br />FSSC",
                        "de": "Mit freundlichen Grüßen,<br />FSSC",
                    }

                    for loc in mail_body["salutation"]:
                        mail_body["salutation"][loc] = mail_body["salutation"][
                            loc
                        ].format(recipient_name)
                    for loc in mail_body["body"]:
                        mail_body["body"][
                            loc
                        ] = """{}. {} <a href="mailto:{}">{}</a>.""".format(
                            mail_body["body"][loc],
                            mail_body_feedback[loc],
                            config.GMAIL_ADDEXPENSE_REPLYTO,
                            config.GMAIL_ADDEXPENSE_REPLYTO,
                        )

                    message = (
                        gmail_service.users()
                        .messages()
                        .send(
                            userId="me",
                            body=self.generate_mail(
                                afas_data["email_address"], mail_body, locale
                            ),
                        )
                        .execute()
                    )
                    logging.info(
                        f"Email '{message['id']}' for expense '{expense_id}' has been sent"
                    )
                except errors.HttpError as e:
                    logging.error(
                        "An exception occurred when sending an email: {}".format(e)
                    )
                except Exception as e:
                    logging.error("An error occurred: {}".format(e))
            else:
                logging.info("Gmail service could not be created")
        else:
            logging.info("Dev mode active for sending e-mails")

    def send_notification(
        self, notification_type, afas_data, expense_id, manager_type="linemanager"
    ):
        recipient = None
        notification_body = None

        if notification_type == "assess_expense":
            if manager_type == "leasecoordinator" and hasattr(
                config, "GMAIL_LEASECOORDINATOR_ADDRESS"
            ):
                recipient_mail = config.GMAIL_LEASECOORDINATOR_ADDRESS
                recipient = {
                    "upn": recipient_mail,
                    "email_address": recipient_mail,
                    "Voornaam": "Lease Coördinator",
                }
            elif "Manager_personeelsnummer" in afas_data:
                query = self.ds_client.query(kind="AFAS_HRM")
                query.add_filter(
                    "Personeelsnummer", "=", afas_data["Manager_personeelsnummer"]
                )
                db_data = list(query.fetch(limit=1))

                if len(db_data) == 1:
                    recipient = db_data[0]

            notification_body = {
                "title": {
                    "nl": "Nieuwe declaratie",
                    "en": "New expense",
                    "de": "Neue Spesenabrechnung",
                },
                "body": {
                    "nl": "Er staat een nieuwe declaratie klaar om beoordeeld te worden",
                    "en": "A new expense is ready for assessment",
                    "de": "Eine neue Spesenabrechnung ist eingereicht worden und wartet auf Genehmigung",
                },
            }
        elif notification_type == "rejected_expense":
            recipient = afas_data
            notification_body = {
                "title": {
                    "nl": "Aanpassing vereist",
                    "en": "Adjustment needed",
                    "de": "Anpassung erforderlich",
                },
                "body": {
                    "nl": "Je declaratie is niet goedgekeurd. Het is nodig deze aan te passen",
                    "en": "Your expense has not been approved. An adjustment is necessary",
                    "de": "Ihre Spesenabrechnung ist nicht genehmigt worden. Es ist erforderlich, dass diese geändert wird",
                },
            }

        if recipient and "upn" not in recipient:
            query = self.ds_client.query(kind="AFAS_HRM")
            query.add_filter("Personeelsnummer", "=", recipient["Personeelsnummer"])
            db_data = list(query.fetch(limit=1))

            if len(db_data) == 1:
                recipient = db_data[0]

        if (
            notification_body
            and recipient
            and "upn" in recipient
            and "email_address" in recipient
        ):
            if manager_type == "leasecoordinator":
                locale = "nl"
                notification_status = False
            else:
                locale = self.get_employee_locale(recipient["upn"].strip())
                notification_status = self.send_push_notification(
                    notification_body, recipient, expense_id, locale
                )

            if not notification_status:
                self.send_mail_notification(
                    notification_body, recipient, expense_id, locale
                )
        else:
            logging.info(f"No notification sent for expense '{expense_id}'")

    def get_employee_profile(self):
        if "unique_name" not in self.employee_info:
            return make_response_translated(
                "Unieke identificatie niet in token gevonden", 403
            )

        key = self.ds_client.key("EmployeeProfiles", self.employee_info["unique_name"])
        employee_profile = self.ds_client.get(key)

        if not employee_profile:
            return make_response_translated("Medewerker profiel niet gevonden", 403)

        return make_response(
            jsonify({"locale": employee_profile.get("locale", "")}), 200
        )

    def add_employee_profile(self, employee_profile):
        if "unique_name" not in self.employee_info:
            return make_response_translated(
                "Unieke identificatie niet in token gevonden", 403
            )

        key = self.ds_client.key("EmployeeProfiles", self.employee_info["unique_name"])
        entity = datastore.Entity(key=key)
        entity.update(
            {
                "locale": employee_profile.locale,
                "last_updated": datetime.datetime.utcnow().isoformat(timespec="seconds")
                + "Z",
            }
        )
        self.ds_client.put(entity)

        return make_response("", 201)

    def register_push_token(self, push_token):
        if "unique_name" not in self.employee_info:
            return make_response_translated(
                "Unieke identificatie niet in token gevonden", 403
            )

        push_identifier = "{}_{}_{}".format(
            self.employee_info["unique_name"],
            push_token["device_id"],
            push_token["bundle_id"],
        )
        unique_id = hashlib.sha256(push_identifier.encode("utf-8")).hexdigest()

        key = self.ds_client.key("PushTokens", str(unique_id))
        entity = datastore.Entity(key=key)

        entity.update(
            {
                "device_id": push_token.get("device_id", None),
                "bundle_id": push_token.get("bundle_id", None),
                "os_platform": push_token.get("os_platform", None),
                "os_version": push_token.get("os_version", None),
                "push_token": push_token.get("push_token", None),
                "app_version": push_token.get("app_version", None),
                "unique_name": self.employee_info["unique_name"],
                "last_updated": datetime.datetime.utcnow().isoformat(timespec="seconds")
                + "Z",
            }
        )
        self.ds_client.put(entity)

        return make_response("", 201)


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
            "employee.email", "=", self.employee_info["unique_name"]
        )
        expense_data = self._process_expenses_info(expenses_info)

        if expense_data:
            return expense_data

        return make_response("", 204)

    def _prepare_context_update_expense(self, expense):
        # Check if expense is from employee
        if not expense["employee"]["email"] == self.employee_info["unique_name"]:
            return {}, {}

        # Check if status update is not unauthorized
        allowed_status_transitions = {
            "draft": ["draft", "ready_for_manager", "ready_for_creditor", "cancelled"],
            "rejected_by_manager": [
                "rejected_by_manager",
                "ready_for_manager",
                "ready_for_creditor",
                "cancelled",
            ],
            "rejected_by_creditor": [
                "rejected_by_creditor",
                "ready_for_manager",
                "ready_for_creditor",
                "cancelled",
            ],
        }

        if expense["status"]["text"] in allowed_status_transitions:
            fields = {
                "status",
                "cost_type",
                "note",
                "transaction_date",
                "amount",
                "manager_type",
                "flags",
            }
            return fields, allowed_status_transitions[expense["status"]["text"]]

        return {}, {}

    def add_attachment(self, expense_id, data):
        expense_key = self.ds_client.key("Expenses", expense_id)
        expense = self.ds_client.get(expense_key)
        if not expense:
            return make_response_translated("Declaratie niet gevonden", 404)
        if expense["employee"]["email"] != self.employee_info["unique_name"]:
            return make_response_translated("Ongeautoriseerd", 403)

        creation = self.create_attachment(
            data, expense.key.id_or_name, self.employee_info["unique_name"]
        )

        if not creation:
            return make_response_translated(
                "Er ging iets fout tijdens het uploaden van bestanden", 400
            )
        return 201


class ManagerExpenses(ClaimExpenses):
    def _check_attachment_permission(self, expense):
        cost_type_entity, cost_type_active = self._process_cost_type(
            expense["cost_type"]
        )
        manager_type = "linemanager"

        if cost_type_entity is not None:
            manager_type = cost_type_entity.get("ManagerType", "")

        if (
            "leasecoordinator.write" in self.employee_info.get("scopes", [])
            and manager_type == "leasecoordinator"
        ):
            return True

        return (
            expense["employee"]["afas_data"]["Manager_personeelsnummer"]
            == self.get_manager_identifying_value()
        )

    def _process_expenses_info(self, expenses_info):
        expenses_data = expenses_info.fetch()
        if expenses_data:
            cost_type_list = list(self.ds_client.query(kind="CostTypes").fetch())

            expenses_list = []
            for ed in expenses_data:

                cost_type_entity, cost_type_active = self._process_cost_type(
                    ed["cost_type"], cost_type_list
                )
                cost_type = (
                    None if cost_type_entity is None else cost_type_entity.key.name
                )

                expenses_list.append(
                    {
                        "id": ed.id,
                        "amount": ed["amount"],
                        "note": ed["note"],
                        "cost_type": cost_type,
                        "claim_date": ed["claim_date"],
                        "transaction_date": ed["transaction_date"],
                        "employee": ed["employee"]["full_name"],
                        "status": self._merge_rejection_note(ed["status"]),
                        "manager_type": ed.get("manager_type"),
                        "flags": ed.get("flags", {}),
                    }
                )
            return expenses_list
        return []

    def __init__(self):
        super().__init__()
        self.manager_number = self.get_manager_identifying_value()

    def get_manager_identifying_value(self):
        afas_data = self.get_employee_afas_data(self.employee_info["unique_name"])
        if afas_data:
            return afas_data["Personeelsnummer"]

        return None

    def get_all_expenses(self):
        expense_data = []

        # Fetch configured managers
        configured_managers = config.AFAS_DATA_EMEND.get("managers", dict())
        if str(self.manager_number) in configured_managers:
            employees = configured_managers[str(self.manager_number)].get("employees", list())
            expenses_query = self._create_expenses_query()

            expenses_query.add_filter("status.text", "=", "ready_for_manager")
            for employee in employees:
                expenses_query.add_filter("employee.afas_data.Personeelsnummer", "=", int(employee))

            expense_data += self._process_expenses_info(expenses_query)

        # Retrieve manager's expenses
        expenses_info = self._create_expenses_query()
        expenses_info.add_filter("status.text", "=", "ready_for_manager")
        expenses_info.add_filter(
            "employee.afas_data.Manager_personeelsnummer", "=", self.manager_number
        )

        for expense in self._process_expenses_info(expenses_info):
            if (
                "manager_type" in expense
                and expense["manager_type"] == "leasecoordinator"
            ):
                continue

            expense_data.append(expense)

        # Retrieve lease coordinator's expenses if correct role
        if "leasecoordinator.write" in self.employee_info.get("scopes", []):
            expenses_lease = self._create_expenses_query()
            expenses_lease.add_filter("manager_type", "=", "leasecoordinator")
            expenses_lease.add_filter("status.text", "=", "ready_for_manager")

            expense_data = expense_data + self._process_expenses_info(expenses_lease)

            expense_data.sort(key=lambda x: x["claim_date"], reverse=True)

        if expense_data:
            return jsonify(expense_data)

        return make_response("", 204)

    def _prepare_context_update_expense(self, expense):
        # Check if expense is for manager
        if not expense["employee"]["afas_data"][
            "Manager_personeelsnummer"
        ] == self.manager_number and "leasecoordinator.write" not in self.employee_info.get(
            "scopes", []
        ):
            return {}, {}

        # Check if status update is not unauthorized
        allowed_status_transitions = {
            "ready_for_manager": ["ready_for_creditor", "rejected_by_manager"]
        }

        if expense["status"]["text"] in allowed_status_transitions:
            fields = {
                "status",
                "cost_type",
                "rnote",
                "rnote_id",
                "manager_type",
                "flags",
            }
            return fields, allowed_status_transitions[expense["status"]["text"]]

        return {}, {}

    def get_rejection_notes(self):
        """
        Get rejection_notes
        :return:
        """

        if REJECTION_NOTES:
            return jsonify(
                [
                    {
                        "form": REJECTION_NOTES[key].get("form"),
                        "rnote": REJECTION_NOTES[key].get("rnote"),
                        "rnote_id": REJECTION_NOTES[key].get("rnote_id"),
                        "translations": REJECTION_NOTES[key].get("translations"),
                    }
                    for key in REJECTION_NOTES
                ]
            )

        return make_response("", 204)


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

            cost_type_list = list(self.ds_client.query(kind="CostTypes").fetch())
            results = []

            for ed in expenses_data:
                cost_type_entity, cost_type_active = self._process_cost_type(
                    ed["cost_type"], cost_type_list
                )
                cost_type = (
                    None if cost_type_entity is None else cost_type_entity.key.name
                )

                logging.debug(f"get_all_expenses: [{ed}]")

                results.append(
                    {
                        "id": ed.id,
                        "amount": ed["amount"],
                        "note": ed["note"],
                        "cost_type": cost_type,
                        "claim_date": ed["claim_date"],
                        "transaction_date": ed["transaction_date"],
                        "employee": ed["employee"]["full_name"],
                        "company_name": ed["employee"]["afas_data"]["Bedrijf"],
                        "department_code": ed["employee"]["afas_data"]["Afdeling Code"],
                        "department_descr": ed["employee"]["afas_data"][
                            "Afdelingsomschrijving"
                        ],
                        "status": self._merge_rejection_note(ed["status"]),
                    }
                )
            return jsonify(results)

        return make_response("", 204)

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
        day_to = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

        if date_from != "1970-01-01":
            day_from = date_from + "T00:00:00Z"
        if date_to != "1970-01-01":
            day_to = date_to + "T23:59:59Z"

        if date_from > date_to:
            return make_response_translated("Startdatum is later dan einddatum", 403)

        expenses_ds = self.ds_client.query(kind="Expenses")
        expenses_ds.add_filter("claim_date", ">=", day_from)
        expenses_ds.add_filter("claim_date", "<=", day_to)
        expenses_data = expenses_ds.fetch()

        query_filter: Dict[Any, str] = dict(
            creditor="ready_for_creditor", creditor2="approved"
        )

        if expenses_data:
            cost_type_list = list(self.ds_client.query(kind="CostTypes").fetch())
            results = []

            for expense in expenses_data:
                expense["status"] = self._merge_rejection_note(expense["status"])

                cost_type_entity, cost_type_active = self._process_cost_type(
                    expense["cost_type"], cost_type_list
                )
                cost_type = (
                    None if cost_type_entity is None else cost_type_entity.key.name
                )

                expense_row = {
                    "id": expense.id,
                    "amount": expense["amount"],
                    "note": expense["note"],
                    "cost_type": cost_type,
                    "claim_date": expense["claim_date"],
                    "transaction_date": expense["transaction_date"],
                    "employee": expense["employee"]["full_name"],
                    "company_name": expense["employee"]["afas_data"]["Bedrijf"],
                    "department_code": expense["employee"]["afas_data"][
                        "Afdeling Code"
                    ],
                    "department_descr": expense["employee"]["afas_data"][
                        "Afdelingsomschrijving"
                    ],
                    "status": expense["status"],
                    "auto_approved": expense.get("auto_approved", ""),
                    "manager": expense.get("employee", {})
                    .get("afas_data", {})
                    .get(
                        "Manager_personeelsnummer", "Manager not found: check expense"
                    ),
                    "export_date": expense["status"].get("export_date", ""),
                    "flags": expense.get("flags", {}),
                }

                expense_row["export_date"] = (expense_row["export_date"], "")[
                    expense_row["export_date"] == "never"
                ]

                if expenses_list == "expenses_creditor":
                    if (
                        query_filter["creditor"] == expense["status"]["text"]
                        or query_filter["creditor2"] == expense["status"]["text"]
                    ):
                        results.append(expense_row)

                if expenses_list == "expenses_all":
                    results.append(expense_row)

            return results

        return make_response("", 204)

    def get_all_expenses_journal(self, date_from, date_to):
        """Get CSV of all the expenses from Expenses_Journal"""
        day_from = "1970-01-01T00:00:00Z"
        day_to = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

        if date_from != "1970-01-01":
            day_from = date_from + "T00:00:00Z"
        if date_to != "1970-01-01":
            day_to = date_to + "T23:59:59Z"

        if date_from > date_to:
            return make_response_translated("Startdatum is later dan einddatum", 403)

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

        return make_response("", 204)

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
                        if "old" in attribute[name] and isinstance(
                            attribute[name]["old"], dict
                        ):
                            for component in attribute[name]["new"]:
                                # Expense has a new component which does not have a 'new' value
                                if component not in attribute[name]["old"]:
                                    changes.append(
                                        {
                                            "Expenses_Id": expense["Expenses_Id"],
                                            "Time": expense["Time"],
                                            "Attribute": name + ": " + component,
                                            "Old value": "",
                                            "New value": str(
                                                attribute[name]["new"][component]
                                            ),
                                            "User": expense.get("User", ""),
                                        }
                                    )
                                # Expense has an old value which differs from the new value
                                elif (
                                    attribute[name]["new"][component]
                                    != attribute[name]["old"][component]
                                ):
                                    changes.append(
                                        {
                                            "Expenses_Id": expense["Expenses_Id"],
                                            "Time": expense["Time"],
                                            "Attribute": name + ": " + component,
                                            "Old value": str(
                                                attribute[name]["old"][component]
                                            ),
                                            "New value": str(
                                                attribute[name]["new"][component]
                                            ),
                                            "User": expense.get("User", ""),
                                        }
                                    )
                        # Expense is completely new
                        else:
                            for component in attribute[name]["new"]:
                                if component == "afas_data":
                                    continue
                                changes.append(
                                    {
                                        "Expenses_Id": expense["Expenses_Id"],
                                        "Time": expense["Time"],
                                        "Attribute": name + ": " + component,
                                        "Old value": "",
                                        "New value": str(
                                            attribute[name]["new"][component]
                                        ),
                                        "User": expense.get("User", ""),
                                    }
                                )

                    except (TypeError, KeyError):
                        logging.warning(
                            "Expense from Expense_Journal does not have the right format: {}".format(
                                expense["Expenses_Id"]
                            )
                        )
                # Expense has an old value which differs from the new value and no nested components
                else:
                    old_value = ""
                    if "old" in attribute[name]:
                        old_value = str(attribute[name]["old"])

                    changes.append(
                        {
                            "Expenses_Id": expense["Expenses_Id"],
                            "Time": expense["Time"],
                            "Attribute": name,
                            "Old value": old_value,
                            "New value": str(attribute[name]["new"]),
                            "User": expense.get("User", ""),
                        }
                    )

        return changes

    def _prepare_context_update_expense(self, expense):
        # Check if status update is not unauthorized
        allowed_status_transitions = {
            "ready_for_creditor": ["rejected_by_creditor", "approved"]
        }

        if expense["status"]["text"] in allowed_status_transitions:
            fields = {
                "status",
                "cost_type",
                "rnote",
                "rnote_id",
                "manager_type",
                "flags",
            }
            return fields, allowed_status_transitions[expense["status"]["text"]]

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
            if (
                datetime.datetime(1970, 1, 1)
                <= form_data.to_dict().get("transaction_date").replace(tzinfo=None)
                <= (datetime.datetime.today() + datetime.timedelta(hours=2)).replace(
                    tzinfo=None
                )
            ):
                html = {
                    '"': "&quot;",
                    "&": "&amp;",
                    "'": "&apos;",
                    ">": "&gt;",
                    "<": "&lt;",
                    "{": "&lbrace;",
                    "}": "&rbrace;",
                }
                form_data.note = "".join(
                    html.get(c, c) for c in form_data.to_dict().get("note")
                )
                form_data.transaction_date = form_data.transaction_date.strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z"
                )
                return expense_instance.add_expenses(form_data)
            return jsonify("Date needs to be between 1970-01-01 and today"), 400
    except Exception:
        logging.exception("Exception on add_expense")
        return jsonify("Something is wrong with the request"), 400


def get_all_creditor_expenses(expenses_list, date_from, date_to):
    """
    Get all expenses
    :rtype: None
    """
    if expenses_list not in ["expenses_creditor", "expenses_all"]:
        return make_response_translated("Geen geldige queryparameter", 400)

    expense_instance = CreditorExpenses()
    expenses_data = expense_instance.get_all_expenses(
        expenses_list=expenses_list, date_from=date_from, date_to=date_to
    )

    format_expense = connexion.request.headers["Accept"]

    return get_expenses_format(
        expenses_data=expenses_data, format_expense=format_expense
    )


def get_all_creditor_expenses_journal(date_from, date_to):
    """
    Get all expenses journal
    :rtype: None
    """
    expense_instance = CreditorExpenses()
    expenses_data = expense_instance.get_all_expenses_journal(
        date_from=date_from, date_to=date_to
    )

    format_expense = connexion.request.headers["Accept"]

    return get_expenses_format(
        expenses_data=expenses_data, format_expense=format_expense
    )


def get_cost_types():  # noqa: E501
    """Get all cost_type
    :rtype: None
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_cost_types()


def get_rejection_notes():  # noqa: E501
    """Get all rejection_notes
    :rtype: None
    """
    expense_instance = ManagerExpenses()
    return expense_instance.get_rejection_notes()


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
            document_id=document_id, document_type=document_type
        )
    except ValueError as e:
        return make_response(str(e), 400)
    except Exception as error:
        logging.exception(f"An exception occurred when retrieving a document: {error}")
        return make_response_translated("Er ging iets fout", 400)
    else:
        if export_file:
            if document_type == "payment_file":
                content_response = {
                    "content_type": "application/xml",
                    "file": MD.parse(export_file.name)
                    .toprettyxml(encoding="utf-8")
                    .decode(),
                }
            elif document_type == "booking_file":
                with open(export_file.name, "r") as file_in:
                    content_response = {
                        "content_type": "text/csv",
                        "file": file_in.read(),
                    }
                    file_in.close()

            mime_type = content_response["content_type"]
            return Response(
                content_response["file"],
                headers={
                    "Content-Type": f"{mime_type}",
                    "charset": "utf-8",
                    "Content-Disposition": f"attachment; filename={document_id}.{mime_type.split('/')[1]}",
                    "Authorization": "",
                },
            )

        return make_response_translated("Document niet gevonden", 404)


def get_expenses_format(expenses_data, format_expense):
    """
    Get format of expenses export: csv/json
    :param expenses_data:
    :param format_expense:
    :param extra_fields:
    :return:
    """
    if not expenses_data:
        return make_response("", 204)

    if isinstance(expenses_data, Response):
        return expenses_data

    if "application/json" in format_expense:
        logging.debug("Creating json table")
        return jsonify(expenses_data)

    if "text/csv" in format_expense:
        logging.debug("Creating csv file")
        try:
            with tempfile.NamedTemporaryFile("w") as csv_file:
                # Set CSV writer and header
                field_names = list(expenses_data[0].keys())
                csv_writer = csv.DictWriter(
                    csv_file,
                    fieldnames=field_names,
                    delimiter=",",
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL,
                )
                csv_writer.writeheader()

                for expense in expenses_data:
                    if "status" in expense:
                        expense["status"] = expense["status"]["text"]

                    for field in expense:
                        if isinstance(expense[field], str):
                            expense[field] = expense[field].replace("\n", " ")

                    csv_writer.writerow(expense)

                csv_file.flush()
                return send_file(
                    csv_file.name,
                    mimetype="text/csv",
                    as_attachment=True,
                    attachment_filename="tmp.csv",
                )
        except Exception:
            logging.exception("Exception on writing/sending CSV in get_all_expenses")
            return make_response_translated("Er ging iets fout", 400)

    return make_response_translated("Verzoek mist een Accept-header", 400)


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
        logging.exception("Exception on update_expenses_creditor")
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
            if "amount" in form_data and isinstance(form_data["amount"], int):
                form_data["amount"] = float(form_data["amount"])

            if form_data.get(
                "transaction_date"
            ):  # Check if date exists. If it doesn't, let if pass.
                if datetime.datetime.strptime(
                    form_data.get("transaction_date"), "%Y-%m-%dT%H:%M:%S.%fZ"
                ) > datetime.datetime.today() + datetime.timedelta(hours=2):
                    return jsonify("Date needs to be in de past"), 400

            if form_data.get(
                "note"
            ):  # Check if note exists. If it doesn't, let if pass.
                html = {
                    '"': "&quot;",
                    "&": "&amp;",
                    "'": "&apos;",
                    ">": "&gt;",
                    "<": "&lt;",
                    "{": "&lbrace;",
                    "}": "&rbrace;",
                }
                form_data["note"] = "".join(
                    html.get(c, c) for c in form_data.get("note")
                )
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
        logging.exception("Exception on update_expense")
        return jsonify("Something went wrong. Please try again later"), 500


def get_expenses_employee(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_expenses(expenses_id, "employee")


def get_expenses_manager(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_expenses(expenses_id, "manager")


def get_expenses_creditor(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_expenses(expenses_id, "creditor")


def get_expenses_controller(expenses_id):
    """Get information from expenses by id
    :rtype: Expenses
    """
    expense_instance = ClaimExpenses()
    return expense_instance.get_expenses(expenses_id, "controller")


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
        logging.exception("Exception on add_attachment")
        return jsonify("Something went wrong. Please try again later"), 500


def api_base_url():
    base_url = request.host_url

    if "GAE_INSTANCE" in os.environ:
        if hasattr(config, "BASE_URL"):
            base_url = config.BASE_URL
        else:
            base_url = f"https://{os.environ['GOOGLE_CLOUD_PROJECT']}.appspot.com/"

    return base_url


def initialise_gmail_service(subject, scopes):
    credentials, project_id = google.auth.default(
        scopes=["https://www.googleapis.com/auth/iam"]
    )
    delegated_credentials = get_delegated_credentials(credentials, subject, scopes)
    gmail_service = googleapiclient.discovery.build(
        "gmail", "v1", credentials=delegated_credentials, cache_discovery=False
    )
    return gmail_service


def get_employee_profile():
    expense_instance = ClaimExpenses()
    return expense_instance.get_employee_profile()


def add_employee_profile():
    if connexion.request.is_json:
        expense_instance = ClaimExpenses()
        employee_profile = EmployeeProfile.from_dict(
            connexion.request.get_json()
        )  # noqa: E501

        return expense_instance.add_employee_profile(employee_profile)

    return make_response_translated("Er ging iets fout", 400)


def register_push_token():
    if connexion.request.is_json:
        expense_instance = ClaimExpenses()
        push_token = json.loads(connexion.request.get_data().decode())  # noqa: E501

        return expense_instance.register_push_token(push_token)

    return make_response_translated("Er ging iets fout", 400)
