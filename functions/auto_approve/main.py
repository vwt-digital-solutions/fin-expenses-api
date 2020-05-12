from google.cloud import datastore
import re
import logging
import json
import datetime
from decimal import Decimal

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
        cost_type_list = {}
        for cost_type in query_cost_type.fetch():
            cost_type_list[int(cost_type.key.name)] = \
                int(cost_type['MinAmount'])
        query.add_filter('claim_date', '<=', boundary)
        query.add_filter('status.text', '=', 'ready_for_manager')

        expenses_to_update = []

        for expense in query.fetch():
            changed = []

            # Only approve those expenses with concurrent cost-types
            cost_type_split = re.search(r"([0-9]{6})", expense['cost_type'])

            if not cost_type_split:
                logging.warning(
                    f"No correct cost_type found for expense {expense.key.id}")
                continue
            else:
                cost_type_id = int(cost_type_split.group(0))

            if cost_type_id not in cost_type_list:
                continue
            else:
                if round(Decimal(expense['amount']), 2) > Decimal(
                        cost_type_list[cost_type_id]):
                    logging.info(f'Auto approving expense {expense.key.id}')

                    old_auto_value = expense['auto_approved'] if \
                        'auto_approved' in expense else 'null'
                    new_auto_value = 'Yes'

                    expense['auto_approved'] = new_auto_value

                    # Update Expenses_Journal: auto_approved and status
                    changed.append({'auto_approved': {"old": old_auto_value,
                                                      "new": new_auto_value}})
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
                            "Time": datetime.datetime.utcnow().isoformat(
                                timespec="seconds") + 'Z',
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
