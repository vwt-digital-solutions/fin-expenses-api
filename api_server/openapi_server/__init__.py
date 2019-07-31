import connexion
from flask_cors import CORS

from api_server.openapi_server import encoder

app = connexion.App(__name__, specification_dir='./openapi/')
app.app.json_encoder = encoder.JSONEncoder
app.add_api('openapi.yaml',
            arguments={'title': 'P2P: Expenses API'},
            pythonic_params=True)
CORS(app.app)
