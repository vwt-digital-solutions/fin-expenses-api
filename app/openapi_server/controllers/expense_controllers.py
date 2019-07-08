from flask import request, jsonify, make_response
from google.cloud import datastore

def dscclient():
    return datastore.Client()

def getexpenses(expense_id):
    dsc = dscclient()
    expenses_info = dsc.query(kind='Expense').add_filter('id', '=', expense_id)
    expenses_data = expenses_info.fetch()
    if expenses_data:
        return jsonify(expenses_data)
    else:
        return make_response(jsonify(None), 204)

def getallexpenses():
    dsc = dscclient()
    expenses_info = dsc.query(kind='Expense')
    expenses_data = expenses_info.fetch()
    if expenses_data:
        results = [{
            'Title': ed.Title,
            'Amount': ed.Amount
        } for ed in expenses_data]
        return jsonify(results)
    else:
        return make_response(jsonify(None), 204)

def addexpenses(data):
    dsc = dscclient()
    key = dsc.key('Expense')
    entity = datastore.Entity(key=key)
    entity.update(data)
    dsc.put(entity)
    return entity, 201

def getattachmentsbyid(attachment_id):
    dsc = dscclient()
    attachment_info = dsc.query(kind='Attachment').add_filter('id', '=', attachment_id)
    attachment_data = attachment_info.fetch()
    if attachment_data:
        return jsonify(attachment_data)
    else:
        return make_response(jsonify(None), 204)

def updateattachmentsbyid(data, attachment_id):
    dsc = dscclient()
    key = dsc.key('Attachment', int(attachment_id))
    entity = datastore.Entity(key=key)
    entity.update(data)
    dsc.put(entity)
    return entity, 201


def deleteattachmentsbyid(attachment_id):
    dsc = dscclient()
    key = dsc.key('Attachment', int(attachment_id))
    dsc.delete(key)
    return 200

def addattachments(data):
    dsc = dscclient()
    key = dsc.key('Attachment')
    entity = datastore.Entity(key=key)
    entity.update(data)
    dsc.put(entity)
    return entity, 201

def getdocumentbyid(document_id):
    dsc = dscclient()
    document_info = dsc.query(kind='Document').add_filter('id', '=', document_id)
    document_data = document_info.fetch()
    if document_data:
        return jsonify(document_data)
    else:
        return make_response(jsonify(None), 204)

def adddocument(data):
    dsc = dscclient()
    key = dsc.key('Document')
    entity = datastore.Entity(key=key)
    entity.update(data)
    dsc.put(entity)
    return entity, 201

