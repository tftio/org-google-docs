"""OAuth2 authentication for Google APIs."""

import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# Required scopes for Docs and Drive APIs
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
]

CONFIG_DIR = Path.home() / ".config" / "org-gdocs-sync"
CREDENTIALS_FILE = CONFIG_DIR / "credentials.json"
TOKEN_FILE = CONFIG_DIR / "token.pickle"


def get_credentials() -> Credentials:
    """Get valid user credentials from storage or initiate OAuth2 flow.

    Returns:
        Valid Google OAuth2 credentials.

    Raises:
        FileNotFoundError: If credentials.json is not found.
    """
    creds = None

    # Load existing token
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    # Refresh or obtain new credentials
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Credentials file not found: {CREDENTIALS_FILE}\n"
                    "Please download OAuth2 credentials from Google Cloud Console.\n"
                    "Run 'sync setup' for instructions."
                )

            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return creds


def setup_credentials() -> None:
    """Interactive setup for credentials."""
    print("Setting up Google API credentials...")
    print()
    print("Please place your OAuth2 credentials JSON file at:")
    print(f"  {CREDENTIALS_FILE}")
    print()
    print("To obtain credentials:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Create a project (or select existing)")
    print("3. Enable Google Docs API and Google Drive API")
    print("4. Create OAuth 2.0 credentials (Desktop app)")
    print("5. Download JSON and save to above location")
    print()

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if CREDENTIALS_FILE.exists():
        print("Credentials file found. Testing authentication...")
        get_credentials()
        print("Authentication successful.")
    else:
        print(f"Waiting for credentials file at: {CREDENTIALS_FILE}")
        raise FileNotFoundError("Please add credentials file first.")


def clear_credentials() -> None:
    """Remove stored authentication token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"Removed: {TOKEN_FILE}")
    else:
        print("No stored credentials to remove.")
