import config
import inspect

from openapi_server.models.expense_data import ExpenseData
from google.cloud import datastore


class BusinessRulesEngine:
    """
    Class based function to house all Business Rules functionality

    """

    def __init__(self):
        pass

    def process_rules(self, data, employee, expense=None):
        expense_data = self.to_dict(data) if isinstance(data, ExpenseData) \
            else data
        self.pao_rule(expense_data, employee)
        self.duplicate_rule(expense_data, employee, expense)

    def pao_rule(self, expense_data, employee):
        if hasattr(config, "CONDITION_PAO_COMPANY") and \
                hasattr(config, "CONDITION_PAO_AMOUNT"):
            if "Bedrijf" in employee and "amount" in expense_data and \
                    employee["Bedrijf"] == config.CONDITION_PAO_COMPANY and \
                    expense_data["amount"] <= config.CONDITION_PAO_AMOUNT:
                raise ValueError(
                    "Het declaratiebedrag moet hoger zijn dan €{},-".format(
                        config.CONDITION_PAO_AMOUNT))

    def duplicate_rule(self, modified_data, employee, original_expense):
        if "draft" == modified_data.get("status", ""):
            return

        check_amount = modified_data.get("amount", original_expense["amount"])
        check_date = modified_data.get("transaction_date", original_expense["transaction_date"])

        expenses_ds = datastore.Client().query(kind="Expenses")

        expenses_ds.add_filter("transaction_date", "=", check_date)
        expenses_ds.add_filter("amount", "=", check_amount)
        expenses_ds.add_filter("employee.afas_data.email_address", "=", employee["email_address"])

        duplicate_expenses = expenses_ds.fetch()
        duplicates = []
        for duplicate in duplicate_expenses:
            if duplicate["status"]["text"] != "draft" and duplicate.id != original_expense.id:
                duplicates.append(duplicate.id)

        return

    def to_dict(self, obj):
        pr = {}
        for name in dir(obj):
            value = getattr(obj, name)
            if not name.startswith('__') and not inspect.ismethod(value):
                pr[name] = value
        return pr
