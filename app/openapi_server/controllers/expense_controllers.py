import json

from flask import request, jsonify
from google.cloud import datastore


def getExpenses(expense_id):
    print('WorkingID: ',  expense_id)
    isUser = expense_id > 0
    return expense_id, (200 if isUser else 404)

def addExpenses(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def getAttachmentsById(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def updateAttachmentsById(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def deleteAttachmentsById(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def addAttachments(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def getDocumentById(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)

def addDocument(expenses_id):
    expenses_id = str(expenses_id)
    erin = "test" in expenses_id
    return expenses_id, (200 if erin else 404)