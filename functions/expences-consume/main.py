import logging
import json
import base64


def topic_to_datastore(request):
    # Extract data from request
    envelope = json.loads(request.data.decode('utf-8'))
    payload = base64.b64decode(envelope['message']['data'])

    # Extract subscription from subscription string
    try:
        subscription = envelope['subscription'].split('/')[-1]
    except Exception as e:
        logging.info('Extract of subscription failed')
        logging.debug(e)
        raise e

    # Extract timestamp from string
    try:
        ts = envelope['message']['publishTime'].\
            split('.')[0].\
            replace('T', ' ').\
            replace('Z', '')
    except Exception as e:
        ts = None
        logging.info('Extract of publishTime failed')
        logging.debug(e)

    logging.info(f'Message received {subscription} at {ts} [{payload}]')

    # Returning any 2xx status indicates successful receipt of the message.
    # 204: no content, delivery successfull, no further actions needed
    return 'OK', 204
