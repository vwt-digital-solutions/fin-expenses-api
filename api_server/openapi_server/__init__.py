# import logging
import connexion
# from flask import request, g
from flask_cors import CORS

from openapi_server import encoder

# try:
#     import googleclouddebugger
#
#     googleclouddebugger.enable()
# except ImportError:
#     pass

app = connexion.App(__name__, specification_dir='./openapi/')
app.app.json_encoder = encoder.JSONEncoder
app.add_api('openapi.yaml',
            arguments={'title': 'P2P: Expenses API'},
            pythonic_params=True)
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
