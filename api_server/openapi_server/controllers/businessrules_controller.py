import config
import inspect
from openapi_server.models.expense_data import ExpenseData


class BusinessRulesEngine:
    """
    Class based function to house all Business Rules functionality

    """

    def __init__(self):
        pass

    def process_rules(self, expense, employee):
        expense = self.to_dict(expense) if isinstance(expense, ExpenseData) \
            else expense

        if hasattr(config, 'CONDITION_PAO_COMPANY') and \
                hasattr(config, 'CONDITION_PAO_AMOUNT'):
            if 'Bedrijf' in employee and 'amount' in expense and \
                    employee['Bedrijf'] == config.CONDITION_PAO_COMPANY and \
                    expense['amount'] <= config.CONDITION_PAO_AMOUNT:
                raise ValueError(
                    'Het minimale bedrag voor een declaratie is €{},-'.format(
                        (config.CONDITION_PAO_AMOUNT + 1)))

    def to_dict(self, obj):
        pr = {}
        for name in dir(obj):
            value = getattr(obj, name)
            if not name.startswith('__') and not inspect.ismethod(value):
                pr[name] = value
        return pr
