import logging
import os

import config
import connexion
from connexion import decorators
from connexion.exceptions import BadRequestProblem
from connexion.utils import is_null
from flask_cors import CORS
from jsonschema import ValidationError
from openapi_server import encoder


class RequestBodyValidator(decorators.validation.RequestBodyValidator):
    """
    This class overrides the default connexion RequestBodyValidator
    so that it returns the complete string representation of the
    error, rather than just returning the error message.

    For more information:
        - https://github.com/zalando/connexion/issues/558
        - https://connexion.readthedocs.io/en/latest/request.html
    """

    def validate_schema(self, data, url):
        if self.is_null_value_valid and is_null(data):
            return None

        try:
            self.validator.validate(data)
        except ValidationError as exception:
            if hasattr(config, "DEBUG_LOGGING") and config.DEBUG_LOGGING:
                logging.error(
                    f"{url} validation error: {exception.message}",
                    extra={"validator": "body"},
                )
            else:
                logging.error(
                    f"{url} validation error: {exception.message}",
                    extra={"validator": "body"},
                )

            raise BadRequestProblem(title="Bad Request", detail=exception.message)

        return None


app = connexion.App(__name__, specification_dir="./openapi/")
app.app.json_encoder = encoder.JSONEncoder
app.add_api(
    "openapi.yaml",
    arguments={"title": "P2P: Expenses API"},
    strict_validation=True,
    validator_map={"body": RequestBodyValidator},
)
if "GAE_INSTANCE" in os.environ:
    CORS(app.app, origins=config.ORIGINS)
else:
    CORS(app.app)


@app.app.after_request
def add_header(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self' fonts.gstatic.com data:; "
        "style-src 'self' fonts.googleapis.com 'unsafe-inline'; "
        "style-src-elem 'self' fonts.googleapis.com 'unsafe-inline'; "
        "connect-src 'self'; form-action 'none'; frame-src data:; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
    response.headers["Feature-Policy"] = (
        "geolocation 'none'; midi 'none'; notifications 'none'; push 'none'; "
        "sync-xhr 'none'; microphone 'none'; camera 'none'; "
        "magnetometer 'none'; gyroscope 'none'; speaker 'none'; vibrate 'none'; "
        "fullscreen 'none'; payment 'none';"
    )
    return response
