import openapi_server

from cache_control import CacheControl
from audit_log import AuditLog

app = openapi_server.app

AuditLog(app)
CacheControl(app)
