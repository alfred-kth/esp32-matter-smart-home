# Uppgiftslista: Matter-enhet med ESP32-C6

## Fas 1: Installation och Konfiguration av Utvecklingsmiljön
- [ ] **Installera förkrav**: Installera nödvändiga paket på macOS (Homebrew, git, wget, ninja, python3, etc.).
- [ ] **Installera ESP-IDF**:
  - [ ] Klona ESP-IDF-repositoriet (v5.1+ rekommenderas).
  - [ ] Kör `install.sh` för att ladda ner verktyg.
  - [ ] Lägg till `. export.sh` i shell-profilen.
- [ ] **Installera ESP-Matter SDK**:
  - [ ] Klona `esp-matter` repositoriet med `--recursive`.
  - [ ] Kör `install.sh` i esp-matter för att bygga Matter-verktyg (`bootstrap.sh` körs internt, detta bygger ZAP-verktyget och andra chip-beroenden).
  - [ ] Konfigurera miljövariabler med `source export.sh` i esp-matter-katalogen.

## Fas 2: Prototyping och Test av Exempel
- [ ] **Konfigurera projektet för ESP32-C6**:
  - [ ] Navigera till ett exempel, t.ex. `esp-matter/examples/light`.
  - [ ] Kör `idf.py set-target esp32c6` för att ställa in byggmålet för rätt mikrokontroller.
- [ ] **Bygg och Flasha**:
  - [ ] Kör `idf.py build` för att kompilera koden.
  - [ ] Anslut ESP32-C6 till datorn via USB.
  - [ ] Flasha koden med `idf.py -p <PORT> flash monitor` (byt ut `<PORT>` mot aktuell serieport).
- [ ] **Driftsättning (Commissioning)**:
  - [ ] Läs av terminalutmatningen för att hitta Matter QR-koden länk, eller manuell parningskod (setup payload).
  - [ ] Använd en smartphone (t.ex. med Apple Home eller Google Home) för att driftsätta enheten (Provisioning). Detta konfigurerar enhetens Wi-Fi-uppgifter via BLE.

## Fas 3: Utveckling av Custom Device
- [ ] **Skapa nytt projekt**:
  - [ ] Skapa en ny projektkatalog, t.ex. i `~/Documents/ESP-matter-devices/`.
  - [ ] Kopiera ett lämpligt exempel som grund och uppdatera `CMakeLists.txt` för att inkludera esp-matter-komponenter.
- [ ] **Anpassa Matter Data Model**:
  - [ ] Konfigurera endpoints och clusters (t.ex. On/Off, Level Control, Color Control) i `app_main.cpp`.
  - [ ] (Valfritt) Använd ZAP-verktyget för att generera `.zap`-filer ifall du använder datamodell-generering från Connectedhomeip-repositoriet.
- [ ] **Implementera hårdvarustyrning**:
  - [ ] Skapa drivrutiner för din specifika hårdvara (t.ex. reläer för att tända/släcka lampor, eller PWM/WS2812 för ljusstyrning/färg).
  - [ ] Skriv callbacks (t.ex. `app_driver_attribute_update`) för att ta emot kommandon från Matter-controllern och ändra enhetens fysiska status.

## Fas 4: Nätverk, Säkerhet och OTA
- [ ] **Säkerhetscertifikat (DAC)**:
  - [ ] Använd testcertifikat i utvecklingsfasen.
  - [ ] Generera egna Device Attestation Certificates (DAC) för produktion (kräver egen certifikatauktoritet eller användning av Espressif's tjänster).
- [ ] **OTA-uppdateringar**:
  - [ ] Aktivera OTA Requestor-funktionen i Matter så att enheten kan ladda ner och installera ny firmware trådlöst.
  - [ ] Kompilera och ladda upp en OTA-image.

## Fas 5: Slutlig Testning
- [ ] **Testa Edge Cases**:
  - [ ] Simulera Wi-Fi-bortfall och säkerställ att enheten återansluter korrekt.
  - [ ] Testa strömavbrott (persistens av attribut som on/off-status).
  - [ ] Implementera och testa "Factory Reset"-sekvens (t.ex. hålla in en knapp i 10 sekunder).
- [ ] **Interoperabilitet**:
  - [ ] Testa enheten i flera olika Matter-ekosystem (Apple Home, Google Home, Amazon Alexa, SmartThings) för att garantera kompatibilitet.
