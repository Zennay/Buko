# Blendbook

De werkende pilot staat in runtime/. Start met Python 3.10+ met tijdzonegegevens voor Europe/Amsterdam. Er zijn geen externe Python-pakketten nodig.

    python3 runtime/app.py

Open http://127.0.0.1:8787 voor de website en registreer op /aanmelden met een bedrijfscode en wachtwoord. Registratie en boekingen vereisen geen betaalgegevens of SMTP. Voor handmatige provisioning kun je ook python3 runtime/app.py --create studio gebruiken. Bewaar in dat geval de eenmalig getoonde beheersleutel. Open http://127.0.0.1:8787/admin en gebruik bedrijfscode studio. Elke nieuwe bedrijfscode heeft een eigen agenda en sleutel. Het dashboard toont het publieke boekingsadres en de inline embedcode. Het formulier neemt het lettertype van de hostpagina over en ondersteunt de CSS-variabele --blendbook-color.

SQLite bewaart de gegevens in de huidige map. Gebruik BLENDBOOK_DB voor een vaste locatie. De server luistert op localhost. Gebruik voor een publieke pilot een HTTPS-reverseproxy, toegangs- en volumelimieten, back-ups en een geschikt productieproces.

De weekplanning gebruikt Nederlandse tijd. Een venster reserveert ook de volledige dienstduur na de laatst mogelijke aankomst. Per boeking wordt de ingestelde reistijd aan beide kanten vastgelegd. Gelijktijdige reserveringen worden in een schrijftransactie opnieuw gecontroleerd.

## Huisstijl en beheer

Open /admin met de werkruimtesleutel. Onder Ontwerp voor je website analyseert Blendbook de publiek toegankelijke HTTPS-pagina en maximaal drie gekoppelde stylesheets. De server stuurt alleen bemonsterde kleurcodes en lettertypewaarden naar de AI-provider. Publiceer één van de drie previews. Het publieke formulier haalt het gekozen thema op. Sites die uitsluitend via JavaScript stijlen toevoegen kunnen geen bruikbaar resultaat opleveren.

De quotaperiode volgt de Nederlandse kalendermaand. Registraties die via hetzelfde geverifieerde e-mailadres zijn aangemaakt delen het quotum. Gebruik bij handmatige provisioning dezelfde --owner voor alle werkruimtes van één persoon. Een geslaagde generatie is opnieuw opvraagbaar. Een mislukte providerrespons geeft het quotum vrij. De gekozen variant blijft actief na de maandwisseling.

## Agenda, e-mail en klantbeheer

Een bezoeker krijgt een privélink om te verplaatsen, annuleren of een ICS-bestand te downloaden. Oudere boekingen uit versie 2 behouden hun plaats in de agenda; daarvoor bestaat nog geen klantlink. In het dashboard koppelt de ondernemer de primaire Google- of Microsoft-agenda via OAuth. Blendbook leest bezette tijden en controleert vóór elke boeking opnieuw. Bij een onbereikbare gekoppelde agenda geeft de planner een foutmelding. De koppeling leest de primaire agenda; automatisch aanmaken of bijwerken van externe afspraken staat nog open.

Bevestiging, wijziging, annulering en aanmeldlinks worden transactioneel klaargezet. De mailworker verstuurt met STARTTLS en probeert tijdelijke fouten later opnieuw. Het platform gebruikt de geconfigureerde afzender. Selfservice via /aanmelden verifieert het e-mailadres vooraf. Een nieuwe login via e-mail roteert de beheersleutel voor die werkruimte.

## Op je eigen site

Open het dashboard op de publieke HTTPS-installatie. Sla de diensten, openingstijden en boekingsregels op. Kopieer de insluitcode uit ‘Op je website’ en plak deze in een HTML-blok dat scripts toestaat. Controleer op de gepubliceerde pagina een proefboeking en open de beheerlink om deze te verplaatsen en annuleren.

Koppel Google of Outlook voor controle op bezette tijden. Maak daarnaast onder ‘Boekingen in je agenda tonen’ een privélink. Voeg deze als URL-abonnement toe aan de agenda waarin je Blendbook wilt bekijken. De agenda-app bepaalt wanneer wijzigingen verschijnen. De link bevat een geheim en kan via het dashboard worden ingetrokken. Het abonnement toont dienst en tijdvak en bevat geen contactgegevens.

## Serverconfiguratie

De boekingskern gebruikt de standaardbibliotheek. Installeer daarnaast python3-cryptography voor agenda-OAuth en de integratietests. Kopieer deploy/platform.env.example naar ~/.config/blendbook/platform.env en bescherm het bestand met modus 0600. Gebruik voor BLENDBOOK_TOKEN_KEY een Fernet-sleutel, bijvoorbeeld gegenereerd met Python cryptography. Registreer bij beide OAuth-providers de exacte HTTPS-callback op /oauth/callback. Gebruik bij Google de Calendar API, bij Microsoft gedelegeerde Calendars.ReadBasic en offline_access. Configureer een SMTP-afzender en stel het publieke HTTPS-adres in voor toegang via e-mail.

De systemd-userunits in deploy/ verwachten de code onder ~/blendbook-pilot en bewaren de database daar. De webunit luistert op 127.0.0.1:18786. Activeer de mailtimer zodra SMTP werkt. Gebruik een TLS-reverseproxy met aanvraaglimieten en time-outs vóór publieke lancering. Bewaar back-ups van de database en encryptiesleutel apart. Een volledige end-to-endtest met echte agenda’s en een testmailbox hoort bij de ingebruikname.

    python3 -m unittest discover -s tests -v

De browserinterface voor de pilot staat in runtime/. De oorspronkelijke React-ontwerpstudie blijft beschikbaar in src/ via npm run dev.

Openstaand voor de commerciële lancering zijn onder andere tweerichtingssynchronisatie, herinneringen, een afzenderdomein per ondernemer en betalingen.

Het klantdashboard bevat een maandoverzicht, zoekbare boekingen, verplaatsen en annuleren, dienstbeheer, meerdere tijdblokken, datumuitzonderingen, een handmatige huisstijleditor en aanpasbare boekingsmailtekst. De homepage bevat een lokale interactieve voorbeelddemo. De eigen boekingspagina staat op /boeken?bedrijf=BEDRIJF. AI-generatie voor een wachtwoordaccount vereist een geverifieerd e-mailadres. Dezelfde geverifieerde eigenaar deelt het maandquotum. Configureer een HTTPS-adres en SMTP om verificatiemails te verzenden. Een nieuwe aanmelding roteert de werkruimtesleutel.

Bij hosting op een IP-adres kun je BLENDBOOK_OAUTH_CALLBACK instellen op een HTTPS-domeinroute die naar /oauth/callback op dezelfde server verwijst. Registreer exact die callback bij beide providers. Het dashboard blijft bereikbaar op BLENDBOOK_PUBLIC_URL.

### Kalender koppelen via ICS
Installeer voor agendalink-import op Ubuntu de pakketten python3-cryptography en python3-recurring-ical-events (inclusief icalendar). De dashboardpagina Integraties ondersteunt Google Agenda en Outlook via een door de provider gehost HTTPS-adres dat eindigt op .ics. BLENDBOOK_TOKEN_KEY beschermt de opgeslagen URL. Buko leest de feed bij het opvragen van tijden en opnieuw bij het boeken. Herhalingen, afzeggingen, hele dagen en transparante afspraken volgen de iCalendar-gegevens. Publicatiefrequentie en gedeelde gegevens worden door de provider bepaald. Bij een onleesbare feed wordt boeken geblokkeerd. Een privélink vanuit Buko onder Afspraken exporteren werkt in de andere richting. Voor OAuth blijven de afzonderlijke provider-appgegevens vereist.
