# import logging
import logging

import connexion
# from flask import request, g
from connexion import problem
from connexion.decorators.validation import RequestBodyValidator
from connexion.utils import is_null
from flask_cors import CORS
from jsonschema.validators import validator_for

from openapi_server import encoder


# try:
#     import googleclouddebugger
#
#     googleclouddebugger.enable()
# except ImportError:
#     pass


class LimitedRequestBodyValidator(RequestBodyValidator):

    def validate_schema(self, data, url):
        if self.is_null_value_valid and is_null(data):
            return None

        cls = validator_for(self.schema)
        cls.check_schema(self.schema)
        errors = tuple(cls(self.schema).iter_errors(data))

        if errors:
            logging.exception(f'Exception on {url} - LimitedRequestBodyValidator')
            return problem(400, 'Bad Request', f'Some data is missing or incorrect at {url}', type='Validation')

        return None


validator_map = {
    'body': LimitedRequestBodyValidator,
}

app = connexion.App(__name__, specification_dir='./openapi/')
app.app.json_encoder = encoder.JSONEncoder
app.add_api('openapi.yaml',
            arguments={'title': 'P2P: Expenses API'},
            strict_validation=True,
            validate_responses=True,
            pythonic_params=True, validator_map=validator_map)
CORS(app.app)

# @app.app.before_request
# def before_request():
#     g.user = ''
#     g.ip = ''
#     g.token = {}
#
#
# @app.app.after_request
# def after_request_callback(response):
#     if 'x-appengine-user-ip' in request.headers:
#         g.ip = request.headers.get('x-appengine-user-ip')
#
#     logger = logging.getLogger('auditlog')
#     auditlog_list = list(filter(None, [
#         f"Request Url: {request.url}",
#         f"IP: {g.ip}",
#         f"User-Agent: {request.headers.get('User-Agent')}",
#         f"Response status: {response.status}",
#         f"UPN: {g.user}"
#     ]))
#
#     logger.info(' | '.join(auditlog_list))
#
#     return response
