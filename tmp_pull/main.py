import json
import logging
import os
from threading import Thread

from google.cloud import pubsub_v1, datastore
from google.api_core import exceptions

TOPIC_PROJECT_ID = 'vwt-d-gew1-odh-hub'
DEP_SUBSCRIPTION_NAME = 'vwt-d-gew1-odh-hub-afas-csv3-pull-sub'
EMP_SUBSCRIPTION_NAME = 'vwt-d-gew1-odh-hub-afas-csv1-pull-sub'


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
    def populate_from_payload(entity, payload):
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
        return 'AFAS_HRM', payload['email_address']


class DepartmentProcessor(DBProcessor):

    def __init__(self):
        DBProcessor.__init__(self)

    @staticmethod
    def selector():
        return 'department'

    def identity(self, payload):
        return 'Departments', payload['Afdeling']


def read_topic_dep(subscription_name):
    client = pubsub_v1.SubscriberClient()
    subscription = client.subscription_path(TOPIC_PROJECT_ID,
                                            subscription_name)
    logging.info('Start polling departments')
    parser = DepartmentProcessor()

    while True:
        try:
            response = client.pull(subscription, 10)
        except exceptions.DeadlineExceeded:
            continue

        ack_ids = []
        for message in response.received_messages:
            mdata = json.loads(message.message.data)
            parser.process(mdata)
            ack_ids.append(message.ack_id)
        if ack_ids:
            client.acknowledge(subscription, ack_ids)
    pass


def read_topic_emp(subscription_name):
    client = pubsub_v1.SubscriberClient()
    subscription = client.subscription_path(TOPIC_PROJECT_ID,
                                            subscription_name)
    logging.info('Start polling employees')
    parser = EmployeeProcessor()

    while True:
        try:
            response = client.pull(subscription, 10)
        except exceptions.DeadlineExceeded:
            continue

        ack_ids = []
        for message in response.received_messages:
            mdata = json.loads(message.message.data)
            logging.warn(mdata)
            parser.process(mdata)
            ack_ids.append(message.ack_id)
        if ack_ids:
            client.acknowledge(subscription, ack_ids)
    pass


dep_thread = Thread(target=read_topic_dep, args=DEP_SUBSCRIPTION_NAME)
dep_thread.start()

emp_thread = Thread(target=read_topic_emp, args=EMP_SUBSCRIPTION_NAME)
emp_thread.start()
