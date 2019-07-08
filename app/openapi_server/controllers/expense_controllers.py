from flask import request, jsonify
from google.cloud import datastore


def getexpenses(expense_id):
    dsc = datastore.Client()
    expenses_info = dsc.query(kind='Expenses').add_filter('id', '=', expense_id)
    return jsonify(expenses_info.fetch())

def addexpenses(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def getattachmentsbyid(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def updateattachmentsbyid(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def deleteattachmentsbyid(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def addattachments(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def getdocumentbyid(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def adddocument(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

