# Monitor SharePoint — projekt startowy (Android / iOS + serwer)

## Stan realizacji

Zaimplementowano: interfejs Flutter do przeglądania historii zmian, bezpieczny zapis klucza API w telefonie, odczyt statusu, ręczne uruchomienie skanu; serwer FastAPI z cyklicznym skanowaniem, rekursywnym pobieraniem listy plików Microsoft Graph, bazą SQLite, wykrywaniem nowych, zmodyfikowanych, usuniętych i przeniesionych plików. Pierwszy skan jest bazowy i nie zgłasza fałszywych nowości.

**Niezaimplementowane / wymaga dostępu:** rzeczywiste logowanie Gmail + kod wewnątrz aplikacji, uzyskanie delegowanego tokenu Graph, odświeżanie tokenu, powiadomienia push (FCM/APNs), rozpoznawanie zmiany zawartości po hashu, porównywanie plików w ZIP, instalacyjny APK/IPA. Przycisk „Otwórz SharePoint” otwiera oryginalną stronę logowania, ale **nie przekazuje sesji do serwera**. Bez uprawnionego tokenu Graph automatyczny monitor nie ma dostępu do plików. Nie należy kopiować ciasteczek ani kodów jednorazowych do konfiguracji.

## Uruchomienie serwera (Python 3.11+)

```bash
cd server
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# uzupełnij GRAPH_ACCESS_TOKEN i losowy API_KEY, jeśli uzyskasz legalny dostęp Graph
uvicorn main:app --host 127.0.0.1 --port 8000
```

Na potrzeby telefonu wystaw serwer **wyłącznie przez HTTPS** i z prawidłową kontrolą dostępu. Nie publikuj tokenów Graph. Token w przykładzie wygasa — produkcyjna integracja wymaga obsługi OAuth i odświeżania poświadczeń. Jeśli Graph zwróci 401/403, sprawdź uprawnienia; nie obchodź ograniczeń dostępu.

## Uruchomienie Flutter (Flutter SDK wymagany)

```bash
cd mobile
flutter create --platforms=android,ios .
flutter pub get
flutter run
# budowanie na Androidzie: flutter build apk
```

Dla iOS wymagany jest macOS z Xcode. Po instalacji podaj URL serwera HTTPS i klucz API. W obecnym stanie aplikacja wyświetli dane dopiero po skonfigurowaniu serwera i dostępu Graph.

## Architektura docelowa

1. Uzgodnione logowanie Microsoft Entra External ID / B2B OTP lub inny autoryzowany dostęp do Graph.
2. Serwer z bezpiecznym OAuth, token refresh i ograniczeniem uprawnień do odczytu.
3. Powiadomienia Firebase Cloud Messaging (Android) i APNs (iOS), rejestracja urządzeń, deduplikacja zmian.
4. Harmonogram skanowania i raportowanie błędów; niezależny od pracy telefonu.
5. Testy na rzeczywistym udostępnionym folderze, w tym ZIP, podmiana pliku i uprawnienia gościa.

## Bezpieczeństwo

Projekt nie przechwytuje sesji przeglądarki ani jednorazowych kodów Gmail. API wymaga X-API-Key; do produkcji zalecane są konta użytkowników i rotacja sekretów. Nie udostępniaj pliku .env. Serwer nie pobiera zawartości dokumentów, tylko metadane. Zmiana etag/ctag nie jest kryptograficznym dowodem podmiany treści.

## Automatyczne budowanie APK w GitHub Actions

Projekt zawiera `.github/workflows/android-apk.yml`. Nie musisz instalować Fluttera na swoim komputerze.

1. Utwórz **prywatne** repozytorium GitHub (np. `sharepoint-monitor`) i wgraj do niego **zawartość katalogu `sharepoint_monitor`**. Foldery `mobile`, `server` i `.github` muszą znaleźć się bezpośrednio w katalogu głównym repozytorium. Nie przesyłaj `.env`, kluczy API, tokenów ani firmowych dokumentów.
2. Otwórz w repozytorium **Actions** → **Zbuduj APK Android** → **Run workflow** → **Run workflow**. Uruchomienie nastąpi również automatycznie po zmianach na gałęzi `main` lub `master` w katalogu `mobile`.
3. Po zielonym wyniku otwórz wykonany workflow i w sekcji **Artifacts** pobierz `sharepoint-monitor-android-debug-apk`.
4. Rozpakuj pobrane archiwum. W środku jest `app-debug.apk`. Przenieś go na telefon, otwórz i potwierdź instalację z tego źródła, jeśli Android o to poprosi.

To APK **testowe (debug)**, nie wydanie do sklepu Google Play. Budowanie nie oznacza, że połączenie z SharePointem działa: ekran „Otwórz SharePoint” otwiera oficjalną stronę w przeglądarce, a odczyt zmian nadal wymaga osobnego serwera HTTPS i uprawnionego dostępu Microsoft Graph. Nie ma jeszcze automatycznych powiadomień push ani logowania kodem Gmail wewnątrz aplikacji.
