
from google.cloud import datastore
import logging
import datetime


def process_approve(request):
    if request.args and 'pending' in request.args:
        client = datastore.Client()
        query = client.query(kind='Expenses')
        pending = int(request.args['pending'])
        logging.info(f'Auto-approve claims older than {pending} days')
        boundary = int((datetime.datetime.now() - datetime.timedelta(days=pending))
                       .timestamp()) * 1000
        query.add_filter('date_of_claim', '<=', boundary)
        # only single une-quality criteria, must check programmatically after
        # query.add_filter('status.text', '>', 'approved')
        # query.add_filter('status.text', '<', 'approved')
        for expense in [exp for exp in list(query.fetch())
                        if exp['status']['text'] != 'approve']:
            logging.info(f'Auto approve {expense}')
            expense['status']['text'] = 'approved'
            expense['date_of_transaction'] = int(datetime.datetime.now().timestamp()) * 1000
            logging.info(f'Auto approve {expense}')
            # client.put(expense)
    else:
        problem = {'type': 'MissingParameter',
                   'title': 'Expected time interval for pending approvals not found',
                   'status': 400}
        response = make_response(jsonify(problem), 400)
        response.headers['Content-Type'] = 'application/problem+json',
        return response

