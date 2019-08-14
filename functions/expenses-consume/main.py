import logging
import json
import base64
import os

from google.cloud import datastore


class DBProcessor(object):
    def __init__(self):
        pass

    def process(self, payload):
        client = datastore.Client()
        kind, key = self.identity(payload)
        entity_key = client.key(kind, key)
        entity = client.get(entity_key)

        if entity is None:
            entity = datastore.Entity(key=entity_key)

        self.populate_from_payload(entity, payload)
        client.put(entity)

    def identity(self, payload):
        return '', ''

    @staticmethod
    def populate_from_payload(self, entity, payload):
        for name in payload:
            if hasattr(payload, name):
                entity[name] = payload[name]


class EmployeeProcessor(DBProcessor):

    def __init__(self):
        DBProcessor.__init__(self)

    @staticmethod
    def selector():
        return 'employee'

    def identity(self, payload):
        return 'AFAS_HRM', 'email_address'


class DepartmentProcessor(DBProcessor):

    def __init__(self):
        DBProcessor.__init__(self)

    @staticmethod
    def selector():
        return 'department'

    def identity(self, payload):
        return 'Departments', 'Afdeling'


parsers = {
    EmployeeProcessor.selector(): EmployeeProcessor(),
    DepartmentProcessor.selector(): DepartmentProcessor()
}


selector = os.environ.get('DATA_SELECTOR', 'Required parameter is missed')
verification_token = os.environ['PUBSUB_VERIFICATION_TOKEN']


def topic_to_datastore(request):
    if request.args.get('token', '') != verification_token:
        return 'Invalid request', 400

    # Extract data from request
    envelope = json.loads(request.data.decode('utf-8'))
    payload = base64.b64decode(envelope['message']['data'])

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

    # Extract subscription from subscription string
    try:
        subscription = envelope['subscription'].split('/')[-1]
        logging.info(f'Message received {subscription} at {ts} [{payload}]')

        if selector in parsers:
            parsers[selector].process(payload)

    except Exception as e:
        logging.info('Extract of subscription failed')
        logging.debug(e)
        raise e

    # Returning any 2xx status indicates successful receipt of the message.
    # 204: no content, delivery successfull, no further actions needed
    return 'OK', 204
