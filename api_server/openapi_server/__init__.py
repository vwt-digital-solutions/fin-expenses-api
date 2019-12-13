# import logging
import logging
from typing import AnyStr, Union

import connexion
# from flask import request, g
from connexion import problem
from connexion.decorators.validation import RequestBodyValidator
from connexion.lifecycle import ConnexionResponse
from connexion.utils import is_null, all_json
from flask_cors import CORS
from jsonschema import ValidationError
from jsonschema.validators import validator_for

from openapi_server import encoder


# try:
#     import googleclouddebugger
#
#     googleclouddebugger.enable()
# except ImportError:
#     pass

def validate_schema(self, data, url):
    # type: (dict, AnyStr) -> Union[ConnexionResponse, None]
    """
    @Override default RequestBodyValidator validate_schema. Only used to edit return String.
    @param self:
    @param data:
    @param url:
    @return:
    """
    if self.is_null_value_valid and is_null(data):
        return None

    try:
        self.validator.validate(data)
    except ValidationError as exception:
        logging.error("{url} validation error: {error}".format(url=url,
                                                               error=exception.message),
                      extra={'validator': 'body'})
        return problem(400, 'Bad Request', 'Some data is missing or incorrect', type='Validation')

    return None


RequestBodyValidator.validate_schema = validate_schema

app = connexion.App(__name__, specification_dir='./openapi/')
app.app.json_encoder = encoder.JSONEncoder
app.add_api('openapi.yaml',
            arguments={'title': 'P2P: Expenses API'},
            strict_validation=True)
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
