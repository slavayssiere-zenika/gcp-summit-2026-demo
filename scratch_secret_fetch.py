from google.cloud import secretmanager
import google.auth

credentials, project = google.auth.default()
client = secretmanager.SecretManagerServiceClient(credentials=credentials)
name = f"projects/slavayssiere-sandbox-462015/secrets/admin-password-dev/versions/latest"
response = client.access_secret_version(request={"name": name})
print("SECRET_PWD=" + response.payload.data.decode("UTF-8"))
