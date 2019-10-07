import logging

import openapi_server

from cache_control import CacheControl
from audit_log import AuditLog

app = openapi_server.app
flaskapp = app.app

logging.basicConfig(level=logging.INFO)

AuditLog(app)
CacheControl(app)
