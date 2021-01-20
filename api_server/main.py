import logging
import os
import openapi_server
import google.cloud.logging

from Flask_AuditLog import AuditLog
from Flask_No_Cache import CacheControl
from flask_sslify import SSLify

app = openapi_server.app
flaskapp = app.app


AuditLog(app)
CacheControl(app)
if 'GAE_INSTANCE' in os.environ:
    SSLify(app.app, permanent=True)

    client = google.cloud.logging.Client()
    client.get_default_handler()
    client.setup_logging()

logging.basicConfig(level=logging.INFO)
