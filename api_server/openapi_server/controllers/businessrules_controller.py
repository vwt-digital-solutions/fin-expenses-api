class BusinessRulesEngine:
    """
    Class based function to house all Business Rules functionality

    """

    def __init__(self):
        pass

    def process_rules(self, expense, employee):
        if employee['Bedrijf'] == 'VW TELECOM BV PAO' and \
                expense.amount <= 10:
            raise ValueError(
                'Het minimale bedrag voor een declaratie is €10,-')
