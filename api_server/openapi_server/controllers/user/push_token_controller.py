from connexion import request
from flask import g, make_response, jsonify
from api_server.openapi_server.controllers.translate_responses import make_response_translated

from api_server.openapi_server.models.push_token import PushToken as PushTokenModel
from api_server.openapi_server.database.push_token import PushToken, PushTokenDatabase


PUSH_TOKEN_DB = PushTokenDatabase()


def register_push_token():
    if "unique_name" not in g.token:
        return make_response_translated("Unieke identificatie niet in token gevonden", 403)

    push_token_data = PushTokenModel.from_dict(request.get_json())
    push_token = PushToken.from_push_token_model(push_token_data)

    PUSH_TOKEN_DB.update_push_token_by_user_id(g.token["unique_name"], push_token)

    return make_response("", 201)
