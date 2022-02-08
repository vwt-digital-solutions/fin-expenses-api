from connexion import request
from flask import g, make_response, jsonify
from api_server.openapi_server.controllers.translate_responses import make_response_translated

from api_server.openapi_server.database.user_profile import UserProfileDatabase, UserProfile
from api_server.openapi_server.models.employee_profile import EmployeeProfile as EmployeeProfileModel


EMPLOYEE_PROFILE_DB = UserProfileDatabase()


def get_current_employee_profile():
    if "unique_name" not in g.token:
        return make_response_translated("Unieke identificatie niet in token gevonden", 403)

    profile = EMPLOYEE_PROFILE_DB.get_user_profile(g.token["unique_name"])

    if not profile:
        return make_response_translated("Medewerker profiel niet gevonden", 403)

    return make_response(jsonify(profile.to_response_dict()), 200)


def update_current_employee_profile():
    if "unique_name" not in g.token:
        return make_response_translated("Unieke identificatie niet in token gevonden", 403)

    profile_data = EmployeeProfileModel.from_dict(request.get_json())
    profile = UserProfile.from_employee_profile_model(profile_data)

    EMPLOYEE_PROFILE_DB.update_user_profile(g.token["unique_name"], profile)

    return make_response("", 201)
