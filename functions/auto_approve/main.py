from google.cloud import datastore
import logging
import json
import datetime

from flask import make_response, jsonify
from utils import shift_to_business_days

logging.basicConfig(level=logging.INFO)


def process_approve(request):
    if request.args and 'pending' in request.args:
        client = datastore.Client()
        query = client.query(kind='Expenses')
        pending = int(request.args['pending'])

        logging.info(
            f'Auto-approve claims older than {pending} business days')

        business_pending = shift_to_business_days(pending)
        boundary = (datetime.datetime.now() - datetime.timedelta(
            days=business_pending)).isoformat(timespec="seconds") + 'Z'

        query.add_filter('claim_date', '<=', boundary)
        query.add_filter('status.text', '=', 'ready_for_manager')
        # only single une-quality criteria, must check programmatically after

        expenses_to_update = []
        for expense in query.fetch():
            changed = []

            logging.info(f'Auto approve {expense}')

            if 'auto_approved' in expense:
                old_auto_value = expense['auto_approved']
            else:
                old_auto_value = 'null'
            new_auto_value = 'Yes'

            expense['auto_approved'] = new_auto_value

            # Update Expenses_Journal: auto_approved and status
            changed.append({'auto_approved': {"old": old_auto_value, "new": new_auto_value}})
            changed.append({'status': {"old": expense['status']['text'], "new": 'ready_for_creditor'}})

            expense['status']['text'] = 'ready_for_creditor'

            key = client.key("Expenses_Journal")
            expense_journal = datastore.Entity(key=key)
            expense_journal.update(
                {
                    "Expenses_Id": expense.key.id,
                    "Time": datetime.datetime.utcnow().isoformat(timespec="seconds") + 'Z',
                    "Attributes_Changed": json.dumps(changed)
                }
            )
            expenses_to_update.append(expense)
            expenses_to_update.append(expense_journal)

        client.put_multi(expenses_to_update)
    else:
        problem = {'type': 'MissingParameter',
                   'title': 'Expected time interval for pending approvals not found',
                   'status': 400}
        response = make_response(jsonify(problem), 400)
        response.headers['Content-Type'] = 'application/problem+json',
        return response


if __name__ == '__main__':
    class R:
        def __init__(self):
            self.args = {'pending': 3}
    r = R()
    logging.warning(r.args)
    # r.args = {'pending': 3}
    process_approve(r)
