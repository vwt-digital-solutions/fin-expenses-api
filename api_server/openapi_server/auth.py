from google.auth import iam
from google.auth.transport import requests
from google.oauth2 import service_account

TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'


def get_delegated_credentials(credentials, subject, scopes):
    try:
        creds = credentials.with_subject(subject).with_scopes(scopes)
    except AttributeError:

        request = requests.Request()
        credentials.refresh(request)

        signer = iam.Signer(request, credentials,
                            credentials.service_account_email)
        creds = service_account.Credentials(
            signer, credentials.service_account_email, TOKEN_URI,
            scopes=scopes, subject=subject)
    except Exception:
        raise

    return creds
