import os
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

# pip install --upgrade google-api-python-client oauth2client
# pip install requests
# pip install --upgrade google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2


# Google API-Authentifizierung
SCOPES = ['https://www.googleapis.com/auth/contacts.readonly', 'https://www.googleapis.com/auth/contacts']
SERVICE_ACCOUNT_FILE = 'C:/TEMP/Fotos-DCIM-2023-/_FACE_IDENT/credentials.json'

creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('people', 'v1', credentials=creds)

# Kontakte abrufen
results = service.people().connections().list(
    resourceName='people/me',
    personFields='photos,names'
).execute()

print(results)  # Debug-Ausgabe der gesamten Antwort

profile = service.people().get(resourceName='people/me', personFields='emailAddresses').execute()
print(profile)


connections = results.get('connections', [])

# Ordner zum Speichern der Bilder erstellen
if not os.path.exists('Kontaktbilder'):
    os.makedirs('Kontaktbilder')

# Bilder herunterladen
for person in connections:
    names = person.get('names', [])
    photos = person.get('photos', [])

    # Debug-Ausgabe
    if names:
        name = names[0].get('displayName')
        print(f"Verarbeite Kontakt: {name}")  # Debug-Ausgabe
    else:
        print("Kein Kontaktname gefunden.")

    if photos:
        photo_url = photos[0].get('url')
        response = requests.get(photo_url)
        if response.status_code == 200:
            with open(f'Kontaktbilder/{name}.jpg', 'wb') as f:
                f.write(response.content)
                print(f"{name}.jpg wurde heruntergeladen.")  # Bestätigung
        else:
            print(f"Bild konnte nicht abgerufen werden: {photo_url}")
    else:
        print("Kein Bild für diesen Kontakt vorhanden.")

print("Prozess abgeschlossen.")
