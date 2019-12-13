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

        if 'Bedrijf' in employee and 'amount' in expense and \
                employee['Bedrijf'] == 'VW TELECOM BV PAO' and \
                expense['amount'] <= 10:
            raise ValueError(
                'Het minimale bedrag voor een declaratie is €11,-')

    def to_dict(self, obj):
        pr = {}
        for name in dir(obj):
            value = getattr(obj, name)
            if not name.startswith('__') and not inspect.ismethod(value):
                pr[name] = value
        return pr
