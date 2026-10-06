import os

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ============================================================
# MODIFY THESE VALUES
# ============================================================

CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()

# Drive permissions:
# https://www.googleapis.com/auth/drive
SCOPES = ["https://www.googleapis.com/auth/drive"]

TOKEN_FILE = "token.json"


def get_drive_credentials():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "Imposta GOOGLE_OAUTH_CLIENT_ID e GOOGLE_OAUTH_CLIENT_SECRET."
        )

    credentials = None

    # If we already have a saved token, use it.
    if __import__("os").path.exists(TOKEN_FILE):
        credentials = Credentials.from_authorized_user_file(
            TOKEN_FILE,
            SCOPES
        )

    # If there is no valid token, start OAuth.
    if not credentials or not credentials.valid:

        if credentials and credentials.expired and credentials.refresh_token:
            # Refresh the access token automatically.
            from google.auth.transport.requests import Request
            credentials.refresh(Request())

        else:
            # Start Desktop OAuth flow.
            client_config = {
                "installed": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [
                        "http://localhost"
                    ]
                }
            }

            flow = InstalledAppFlow.from_client_config(
                client_config,
                SCOPES
            )

            # access_type="offline" is what allows Google
            # to issue a refresh token.
            credentials = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent"
            )

        # Save credentials locally.
        with open(TOKEN_FILE, "w") as token:
            token.write(credentials.to_json())

    return credentials


def main():
    credentials = get_drive_credentials()

    # Create the Google Drive API client.
    drive = build(
        "drive",
        "v3",
        credentials=credentials
    )

    # Test the connection by listing files.
    response = drive.files().list(
        pageSize=10,
        fields="files(id, name, mimeType)"
    ).execute()

    files = response.get("files", [])

    print("\nGoogle Drive connection successful!\n")

    if not files:
        print("No files found.")
    else:
        print("Files:")

        for file in files:
            print(
                f"- {file['name']} "
                f"(ID: {file['id']})"
            )


if __name__ == "__main__":
    main()