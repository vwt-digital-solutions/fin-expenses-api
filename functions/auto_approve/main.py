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
        logging.info(f'Auto-approve claims older than {pending} business days')
        business_pending = shift_to_business_days(pending)
        boundary = int((datetime.datetime.now() - datetime.timedelta(days=business_pending))
                       .timestamp()) * 1000
        query.add_filter('date_of_claim', '<=', boundary)
        # only single une-quality criteria, must check programmatically after
        # query.add_filter('status.text', '>', 'approved')
        # query.add_filter('status.text', '<', 'approved')
        for expense in [exp for exp in query.fetch()
                        if exp['status']['text'] == 'ready_for_manager']:
            expense['status']['text'] = 'ready_for_creditor'
            expense['date_of_transaction'] = int(datetime.datetime.now().timestamp()) * 1000
            logging.info(f'Auto approve {expense}')
            client.put(expense)
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
