import config

from google.auth import iam
from google.auth.transport import requests
from google.oauth2 import service_account

TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'  # nosec


def get_delegated_credentials(credentials, subject, scopes):
    try:
        request = requests.Request()
        credentials.refresh(request)

        signer = iam.Signer(request, credentials, config.GMAIL_SERVICE_ACCOUNT)
        creds = service_account.Credentials(
            signer=signer,
            service_account_email=config.GMAIL_SERVICE_ACCOUNT,
            token_uri=TOKEN_URI,
            scopes=scopes,
            subject=subject)
    except Exception:
        raise

    return creds
