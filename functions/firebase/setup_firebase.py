import sys
import config
import logging
import google.auth

from googleapiclient import discovery, errors as gcp_errors
from deepdiff import DeepDiff

logging.getLogger().setLevel(logging.INFO)


class FirebaseSDK:
    def __init__(self):
        self.credentials, self.project = google.auth.default()
        self.project_full = 'projects/{}'.format(self.project)
        self.fb_sdk = discovery.build('firebase', 'v1beta1', credentials=self.credentials)

    def setup(self):
        self.create_firebase_project()  # Create Firebase project

        # Create Firebase apps
        if hasattr(config, 'FIREBASE_APPS') and len(config.FIREBASE_APPS) > 0:
            self.initialize_firebase_apps()

    def create_firebase_project(self):
        project_response = None
        try:
            project_response = self.fb_sdk.projects().get(name=self.project_full).execute()
        except gcp_errors.HttpError:
            pass

        try:
            if not project_response:
                project_body = {
                    'timeZone': 'Europe/Amsterdam',
                    'regionCode': 'NL',
                    'locationId': 'eur3'
                }
                self.fb_sdk.projects().addFirebase(project=self.project_full, body=project_body).execute()
        except gcp_errors.HttpError as e:
            logging.exception(e)
            sys.exit(1)

        logging.info("Firebase is active within GCP project '{}'".format(self.project))

    def initialize_firebase_apps(self):
        list_apps = self.fb_sdk.projects().searchApps(parent=self.project_full).execute()
        list_old_apps = []
        list_new_apps = config.FIREBASE_APPS

        for old_app in list_apps['apps']:
            list_old_apps.append({
                'display_name': old_app['displayName'],
                'platform': old_app['platform'].lower()
            })

        list_diff_apps = DeepDiff(
            list_old_apps, list_new_apps, ignore_order=True, exclude_regex_paths=r"root\[\d+\]\['bundle_id'\]")

        if 'iterable_item_added' in list_diff_apps:
            for key in list_diff_apps['iterable_item_added']:
                app = list_diff_apps['iterable_item_added'][key]

                try:
                    if app['platform'] == 'ios':
                        self.create_firebase_ios_app(app)  # Create iOS app
                    elif app['platform'] == 'android':
                        self.create_firebase_ios_android(app)  # Create Android app
                    else:
                        logging.error("No correct platform found for {} app '{}'".format(
                            app['platform'], app['display_name']))
                except gcp_errors.HttpError as exception:
                    logging.error("Failed adding {} app '{}' to Firebase project '{}'".format(
                        app['platform'], app['display_name'], self.project), str(exception))
                    continue

        logging.info("{} apps are active within Firebase project '{}'".format(len(list_new_apps), self.project))

    def create_firebase_ios_app(self, app):
        app_body = {
            'displayName': app['display_name'],
            'bundleId': app['bundle_id']
        }
        self.fb_sdk.projects().iosApps().create(parent=self.project_full, body=app_body).execute()

    def create_firebase_ios_android(self, app):
        app_body = {
            'displayName': app['display_name'],
            'packageName': app['bundle_id']
        }
        self.fb_sdk.projects().androidApps().create(parent=self.project_full, body=app_body).execute()


FirebaseSDK().setup()
