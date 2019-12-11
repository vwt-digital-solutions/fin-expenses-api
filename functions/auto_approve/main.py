from google.cloud import datastore
import logging
import datetime

from utils import shift_to_business_days

logging.basicConfig(level=logging.INFO)


def process_approve(request):
    if request.args and 'pending' in request.args:
        client = datastore.Client()
        query = client.query(kind='Expenses')
        pending = int(request.args['pending'])
        filter_amount = int(request.args['amount'])
        logging.info(
            f'Auto-approve claims older than {pending} business days with ' +
            f'amount less than {filter_amount}')
        business_pending = shift_to_business_days(pending)
        boundary = (datetime.datetime.now() - datetime.timedelta(
            days=business_pending)).isoformat(timespec="seconds") + 'Z'

        query.add_filter('claim_date', '<=', boundary)
        query.add_filter('status.text', '=', 'ready_for_manager')
        # only single une-quality criteria, must check programmatically after
        # query.add_filter('amount', '<=', filter_amount)

        expenses_to_update = []
        for expense in [exp for exp in query.fetch()
                        if exp['amount'] <= filter_amount]:
            expense['status']['text'] = 'ready_for_creditor'
            expense['date_of_transaction'] = int(
                datetime.datetime.now().timestamp()) * 1000
            logging.info(f'Auto approve {expense}')
            expenses_to_update.append(expense)

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
            self.args = {'pending': 3, 'amount': 200}

    r = R()
    logging.warning(r.args)
    # r.args = {'pending': 3}
    process_approve(r)
