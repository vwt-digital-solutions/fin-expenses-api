from google.cloud import datastore
import logging
import json
import datetime
import re

from flask import make_response, jsonify
from utils import shift_to_business_days

logging.basicConfig(level=logging.INFO)


def process_approve(request):
    if request.args and 'pending' in request.args:
        client = datastore.Client()
        query = client.query(kind='Expenses')
        query_cost_type = client.query(kind="CostTypes")
        pending = int(request.args['pending'])

        logging.info(
            f'Auto-approve claims older than {pending} business days')

        business_pending = shift_to_business_days(pending)
        boundary = (datetime.datetime.now() - datetime.timedelta(
            days=business_pending)).isoformat(timespec="seconds") + 'Z'

        query_cost_type.add_filter('AutoApprove', '=', True)
        cost_types = query_cost_type.fetch()
        grootboek_numbers = []
        for cost_types in cost_types:
            grootboek_numbers.append(cost_types['Grootboek'])

        query.add_filter('claim_date', '<=', boundary)
        query.add_filter('status.text', '=', 'ready_for_manager')

        expenses_to_update = []

        for expense in query.fetch():
            changed = []

            # Only approve those expenses with concurrent cost-types
            grootboek_number = re.search("[0-9]{6}", expense['cost_type']).group()
            if grootboek_number not in grootboek_numbers:
                logging.warning(expense)
                continue

            logging.info(f'Auto approve {expense}')

            if 'auto_approved' in expense:
                old_auto_value = expense['auto_approved']
            else:
                old_auto_value = 'null'
            new_auto_value = 'Yes'

            expense['auto_approved'] = new_auto_value

            # Update Expenses_Journal: auto_approved and status
            changed.append({'auto_approved': {"old": old_auto_value, "new": new_auto_value}})
            changed.append({'status': {
                "old": {'text': expense['status']['text']},
                "new": {'text': 'ready_for_creditor'}}
            })

            expense['status']['text'] = 'ready_for_creditor'

            key = client.key("Expenses_Journal")
            expense_journal = datastore.Entity(key=key)
            expense_journal.update(
                {
                    "Expenses_Id": expense.key.id,
                    "Time": datetime.datetime.utcnow().isoformat(timespec="seconds") + 'Z',
                    "Attributes_Changed": json.dumps(changed),
                    "User": "auto_approved"
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
        response.headers['Content-Type'] = 'application/problem+json'
        return response


if __name__ == '__main__':
    class R:
        def __init__(self):
            self.args = {'pending': 3}

    r = R()
    logging.warning(r.args)
    # r.args = {'pending': 3}
    process_approve(r)
