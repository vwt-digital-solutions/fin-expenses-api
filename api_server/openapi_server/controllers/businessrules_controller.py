import config
import inspect

from datetime import datetime
from openapi_server.models.expense_data import ExpenseData
from google.cloud import datastore


class BusinessRulesEngine:
    """
    Class based function to house all Business Rules functionality

    """

    def __init__(self):
        pass

    def process_rules(self, data, employee, expense=None):
        self.pao_rule(data, employee)
        self.duplicate_rule(data, employee, expense)
        self.employed_rule(employee)

    def pao_rule(self, data, employee):
        expense_data = self.to_dict(data) if isinstance(data, ExpenseData) \
            else data
        if hasattr(config, "CONDITION_PAO_COMPANY") and \
                hasattr(config, "CONDITION_PAO_AMOUNT"):
            if "Bedrijf" in employee and "amount" in expense_data and \
                    employee["Bedrijf"] == config.CONDITION_PAO_COMPANY and \
                    expense_data["amount"] <= config.CONDITION_PAO_AMOUNT:
                raise ValueError(
                    "Het declaratiebedrag moet hoger zijn dan €{},-".format(
                        config.CONDITION_PAO_AMOUNT))

    def employed_rule(self, employee):
        current_day = datetime.today().strftime('%Y-%m-%dT00:00:00Z')
        if 'Datum_uit_dienst' in employee and \
                employee['Datum_uit_dienst'] and \
                employee['Datum_uit_dienst'] < current_day:
            raise ValueError("Dit account is niet meer actief")

    def duplicate_rule(self, modified_data, employee, original_expense=None):
        ds = datastore.Client()

        # Values when expense is new (original_expense = None)
        check_amount = modified_data.get("amount", "")
        check_date = modified_data.get("transaction_date", "")
        expense_id = 0

        # Values when expense is updated (original_expense exists)
        if original_expense is not None:
            check_amount = modified_data.get("amount", original_expense["amount"])
            check_date = modified_data.get("transaction_date", original_expense["transaction_date"])
            expense_id = original_expense.id

        expenses_ds = ds.query(kind="Expenses")

        expenses_ds.add_filter("transaction_date", "=", check_date)
        expenses_ds.add_filter("employee.afas_data.email_address", "=", employee["email_address"])

        duplicate_expenses = expenses_ds.fetch()

        duplicates = []
        for duplicate in duplicate_expenses:
            if duplicate["status"]["text"] not in ["draft", "cancelled"] and \
                    duplicate.id != expense_id and \
                    float(duplicate["amount"]) == float(check_amount):
                duplicates.append(duplicate.id)

        if duplicates:
            modified_data["flags"] = {"duplicates": duplicates}

    def to_dict(self, obj):
        pr = {}
        for name in dir(obj):
            value = getattr(obj, name)
            if not name.startswith('__') and not inspect.ismethod(value):
                pr[name] = value
        return pr
