import config

import openapi_server.models.business_rules as business_rules
from openapi_server.models.business_rules import actions, variables


class BusinessRulesEngine:
    """
    Class based function to house all Business Rules functionality

    """

    def __init__(self):
        business_rules.export_rule_data(ExpenseVariables, ExpenseActions)

        self.business_rules = config.EXPENSE_BUSINESS_RULES

    def process_rules(self, data):
        business_rules.run_all(
            rule_list=self.business_rules,
            defined_variables=ExpenseVariables(data),
            defined_actions=ExpenseActions(data),
            stop_on_first_trigger=True)


class ExpenseActions(actions.BaseActions):
    def __init__(self, expense):
        self.expense = expense

    @actions.rule_action()
    def decline(self, message):
        raise ValueError(message)


class ExpenseVariables(variables.BaseVariables):
    def __init__(self, data):
        self.expense = data['expense']
        self.employee = data['afas_data']

    # EMPLOYEE VARIABLES
    @variables.numeric_rule_variable()
    def employee_personeelsnummer(self):
        return self.employee['Personeelsnummer']

    @variables.numeric_rule_variable()
    def employee_afdeling_code(self):
        return self.employee['Afdeling Code']

    @variables.string_rule_variable()
    def employee_afdeling(self):
        return self.employee['Afdeling']

    @variables.string_rule_variable()
    def employee_afdelingsomschrijving(self):
        return self.employee['Afdelingsomschrijving']

    @variables.string_rule_variable()
    def employee_email_address(self):
        return self.employee['email_address']

    @variables.numeric_rule_variable()
    def employee_manager_personeelsnummer(self):
        return self.employee['Manager_personeelsnummer']

    @variables.string_rule_variable()
    def employee_manager(self):
        return self.employee['Manager']

    @variables.string_rule_variable()
    def employee_naam(self):
        return self.employee['Naam']

    @variables.string_rule_variable()
    def employee_bedrijf(self):
        return self.employee['Bedrijf']

    # EXPENSE VARIABLES
    @variables.numeric_rule_variable()
    def expense_amount(self):
        return self.expense.amount

    @variables.string_rule_variable()
    def expense_cost_type(self):
        return self.expense.cost_type

    @variables.string_rule_variable()
    def expense_date_of_transaction(self):
        return self.expense.date_of_transaction

    @variables.string_rule_variable()
    def expense_note(self):
        return self.expense.note

    @variables.string_rule_variable()
    def expense_transaction_date(self):
        return self.expense.transaction_date
