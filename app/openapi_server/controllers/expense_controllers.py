from flask import jsonify, make_response
from google.cloud import datastore


class Expenses:
    """
    Expenses class that provides functions
    and queries to the tool using google datastore
    """
    def __init__(self):
        self.client = datastore.Client()

    def get_expenses(self, expense_id):
        """Get expenses with expense_id"""
        expenses_info = self.client.query(kind='Expense')\
            .add_filter('id', '=', expense_id)
        expenses_data = expenses_info.fetch()

        if expenses_data:
            return jsonify(expenses_data)
        else:
            return make_response(jsonify(None), 204)

    def get_all_expenses(self):
        """Get JSON of all the expenses"""
        expenses_info = self.client.query(kind='Expense')
        expenses_data = expenses_info.fetch()

        if expenses_data:
            results = [{
                'Title': ed.Title,
                'Amount': ed.Amount
            } for ed in expenses_data]
            return jsonify(results)
        else:
            return make_response(jsonify(None), 204)

    def add_expenses(self, data):
        """Add expense with given data amount and given data note"""
        key = self.client.key('Expense')
        entity = datastore.Entity(key=key)
        entity.update({
                    'ID': entity.key.id_or_name,
                    'Amount': data['amount'],
                    'Note': data['note']
                    })
        self.client.put(entity)
        return make_response(jsonify(entity.key.id_or_name), 201)


expenses_instance = Expenses()
