"""
Genera il refresh token OAuth per Google Drive (uso una sola volta sul PC).

Prerequisiti:
1. Google Cloud Console → APIs → abilita Google Drive API
2. Credenziali → Crea credenziali → ID client OAuth
   - Tipo: App desktop
3. Schermata di consenso OAuth: aggiungi il tuo Gmail come utente di test (se app in Testing)

Uso:
  .\\.venv\\Scripts\\python get_drive_token.py
Poi inserisci Client ID e Client Secret quando richiesti.
Copia l'output nelle variabili Render.
"""
from __future__ import annotations

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://oauth2.googleapis.com/auth/drive"]


def main() -> None:
    print("=== Token Google Drive per Preventivi ===\n")
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    if not client_id or not client_secret:
        raise SystemExit("Client ID e Secret obbligatori.")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    if not creds.refresh_token:
        raise SystemExit(
            "Nessun refresh_token ricevuto. Revoca l'accesso dell'app su "
            "https://myaccount.google.com/permissions e riprova."
        )

    print("\n=== Copia queste variabili su Render ===\n")
    print(f"GOOGLE_OAUTH_CLIENT_ID={client_id}")
    print(f"GOOGLE_OAUTH_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={creds.refresh_token}")
    print("GOOGLE_DRIVE_FOLDER_ID=<id-della-tua-cartella-Drive>")
    print(
        "\nPuoi rimuovere GOOGLE_SERVICE_ACCOUNT_JSON (non serve più).\n"
        "Mantieni SECRET_KEY e APP_PASSWORD."
    )


if __name__ == "__main__":
    main()
