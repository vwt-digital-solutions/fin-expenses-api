# Create Firebase apps

This function is meant to automate the creation of a Firebase project an its iOS and Android applications.

## Configuration
To run this function make sure the following configuration is existing:
1. A `config.py` file that contains the `FIREBASE_APPS` object (see [config.example.py](config.example.py) for an example);
2. A virtualenv with the correct packages installed (see [requirements.txt](requirements.txt));
3. The environment variable `GOOGLE_APPLICATION_CREDENTIALS` with the link towards the GCP service account credentials file;
4. The `roles/firebase.admin` role for the service account used to run this script.

## Run
Use the script below to execute the function:
~~~bash
python3 setup_firebase.py
~~~

## License
This function is licensed under the [GPL-3](https://www.gnu.org/licenses/gpl-3.0.en.html) License