# Inventory Management System for REWE eBons

This project is an Inventory Management System designed specifically for REWE eBons. The system allows users to upload eBons in the form of PDF files, extract the relevant data from the eBons, and store it in a SQLite database. Users can also view, reduce or delete items from the inventory. It also includes a Dockerfile and a Docker Compose file for easy deployment.

## Features

- Upload REWE eBons in PDF format.
- Extract data from uploaded eBons.
- Store extracted data in a SQLite database.
- View all items in the inventory.
- Reduce the quantity of an item.
- Delete an item from the inventory.
- Keep a log of changes made to the inventory.
- Docker support for easy deployment.

## Dependencies

This project is built using Python, Flask and SQLite3. It also uses the PDFPlumber library to extract text from PDF files.

## Installation

First, clone this repository to your local machine:

```bash
git clone https://github.com/Timon-Schneider/Rewe-eBons-Scraper.git
```

Then, navigate into the project directory and install the dependencies:

```bash
cd Rewe-eBons-Scraper
pip install -r requirements.txt
```

## Docker Usage

To build and run the application using Docker, execute the following commands:

```bash
cd Rewe-eBons-Scraper
docker compose up -d
```

Once the server is running, you can access the application at [http://localhost:8888](http://localhost:8888) in your web browser.

## Project Status

This project is currently under development. More features will be added in the future.

---

# Warenverwaltungssystem für REWE eBons

Dieses Projekt ist ein Warenverwaltungssystem, das speziell für REWE eBons entwickelt wurde. Das System ermöglicht es Benutzern, eBons im PDF-Format hochzuladen, die relevanten Daten aus den eBons zu extrahieren und sie in einer SQLite-Datenbank zu speichern. Benutzer können alle Artikel im Inventar anzeigen, die Menge eines Artikels reduzieren oder einen Artikel aus dem Inventar löschen. Es beinhaltet auch eine Dockerfile und eine Docker Compose-Datei für eine einfache Nutzung.

## Funktionen

- Hochladen von REWE eBons im PDF-Format.
- Extrahieren von Daten aus hochgeladenen eBons.
- Speichern der extrahierten Daten in einer SQLite-Datenbank.
- Anzeigen aller Artikel im Inventar.
- Reduzieren der Menge eines Artikels.
- Löschen eines Artikels aus dem Inventar.
- Protokollieren von Änderungen im Inventar.
- Docker-Unterstützung für einfache Nutzung.

## Abhängigkeiten

Dieses Projekt wurde mit Python, Flask und SQLite3 erstellt. Es verwendet auch die PDFPlumber-Bibliothek zum Extrahieren von Text aus PDF-Dateien.

## Installation

Klonen Sie zunächst dieses Repository auf Ihre lokale Maschine:

```bash
git clone https://github.com/Timon-Schneider/Rewe-eBons-Scraper.git
```

Navigieren Sie dann in das Projektverzeichnis und installieren Sie die Abhängigkeiten:

```bash
cd Rewe-eBons-Scraper
pip install -r requirements.txt
```

## Docker-Nutzung

Um die Anwendung mit Docker zu erstellen und auszuführen, führen Sie die folgenden Befehle aus:

```bash
cd Rewe-eBons-Scraper
docker compose up -d
```

Sobald der Server läuft, können Sie die Anwendung in Ihrem Webbrowser unter [http://localhost:8888](http://localhost:8888) aufrufen.

## Projektstatus

Dieses Projekt befindet sich derzeit in der Entwicklung. In Zukunft werden weitere Funktionen hinzugefügt.
