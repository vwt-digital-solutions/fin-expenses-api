import logging
import os
from typing import AnyStr, Union

import connexion
from connexion import problem
from connexion.decorators.validation import RequestBodyValidator
from connexion.lifecycle import ConnexionResponse
from connexion.utils import is_null
from flask_cors import CORS
from jsonschema import ValidationError

from openapi_server import encoder


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
if 'GAE_INSTANCE' in os.environ:
    CORS(app.app, origins=['https://declaratie.test-app.vwtelecom.com', 'https://declaratie.app.vwtelecom.com'])
else:
    CORS(app.app)