# Wild Flame voor Home Assistant

Lokale bediening van **Wild Flame Smart Fire** bio-ethanolhaarden (getest met de Smart Fire A6, 80 cm) vanuit
Home Assistant. Geen cloud: Home Assistant praat rechtstreeks met de haard via diens eigen wifi.

> **Niet officieel.** Dit project is niet gemaakt, goedgekeurd of ondersteund door Wild Flame of AG Solutions.
> Het bedient een apparaat met open vuur. **Gebruik is op eigen risico.** Laat een brandende haard nooit
> onbeheerd achter en volg de veiligheidsvoorschriften van de fabrikant. Het veiligheidssysteem van de haard
> blijft de baas; deze integratie stuurt alleen dezelfde commando's als de officiële app.

## Wat je krijgt

| Entiteit | Wat |
|---|---|
| `switch.<naam>` | Haard aan/uit |
| `number.<naam>_vlamhoogte` | Vlamhoogte 1–10 (niet beschikbaar als de haard niet brandt) |
| `sensor.<naam>_status` | Uit / Opwarmen / Brandt / Afkoelen / Onbekende fase, met eigenschap `since` |
| `sensor.<naam>_laatst_aangezet` | Wanneer de haard voor het laatst is aangezet (blijft staan als hij uit gaat) |
| `sensor.<naam>_brandstofniveau` | Brandstof in % (stappen van 10%) |
| `binary_sensor.<naam>_brandstof_bijna_op` | Aan bij 10% brandstof of minder |
| `sensor.<naam>_kamertemperatuur` | Kamertemperatuur in °C |
| `sensor.<naam>_luchtvochtigheid` | Luchtvochtigheid in % |
| `lock.<naam>_kinderslot` | Kinderslot op de haard: vergrendelen of ontgrendelen |
| `number.<naam>_automatisch_uit_na` | Zet de haard uit na zoveel uur (0 = nooit; instelling) |
| `sensor.<naam>_fasecode` | Ruwe fasecode (diagnostisch) |

### Veiligheid
De haard kent alleen *toggle*- en *stap*-commando's: hetzelfde commando zet hem aan én uit. De integratie leest
daarom altijd eerst de status en stuurt alleen een commando als dat nodig is:
- aanzetten wordt geweigerd tijdens het afkoelen of als het kinderslot aan staat;
- aanzetten wordt ook geweigerd als de haard een onbekende fasecode meldt (mogelijk een storing); de code komt
  in het logboek zodat hij kan worden toegevoegd;
- na een aan/uit- of kinderslot-commando wordt 30 seconden geen tweede gestuurd tot de haard de nieuwe toestand
  meldt;
- de optionele tijd "Automatisch uit na" zet de haard uit als hij zo lang aan staat, ook zonder automatisering;
- de vlamhoogte gaat in losse stappen van 1 met een seconde ertussen, en alleen als de haard brandt.

## Wat je nodig hebt

De haard heeft alleen een eigen wifi-netwerk (`WILDFLAME…`, adres `192.168.4.1`) en komt niet op je
thuisnetwerk. Home Assistant heeft dus een tweede netwerkverbinding met dat wifi nodig, bijvoorbeeld:

- **Een Raspberry Pi met Home Assistant OS via ethernet** (getest): gebruik de ingebouwde wifi voor de haard.
- Een andere computer met een losse wifi-adapter.

### Home Assistant OS verbinden met de wifi van de haard
1. **Instellingen → Systeem → Netwerk → Netwerkinterfaces configureren → WLAN0.**
2. Zoek netwerken, kies `WILDFLAME…`, beveiliging **WPA-PSK**, en vul het wifi-wachtwoord van de haard in.
3. IPv4: **Automatisch**.
4. Laat de ethernet-interface ongewijzigd.

Ethernet blijft je route naar internet; wifi wordt alleen gebruikt voor `192.168.4.x`. De haard accepteert maar
een paar apparaten tegelijk; je telefoon hoeft niet met de haard verbonden te blijven.

> Tip: wordt aanwezigheid in Home Assistant bepaald via je router, zet dan op je telefoon "Verbind automatisch"
> uit voor het wifi van de haard. Anders lijkt het alsof je niet thuis bent zolang je telefoon daarmee verbonden is.

## Installeren

### HACS (aanbevolen)
1. HACS → ⋮ → **Aangepaste repositories** → voeg `https://github.com/stfnw-coding/wildflame-ha` toe, categorie **Integratie**.
2. Installeer **Wild Flame** en herstart Home Assistant.

### Handmatig
Kopieer `custom_components/wildflame` naar `/config/custom_components/wildflame` en herstart Home Assistant.

## Toevoegen
**Instellingen → Apparaten en diensten → Integratie toevoegen → Wild Flame.** Laat het IP-adres op `192.168.4.1`
staan. De integratie controleert direct of de haard bereikbaar is.

## Wat je kunt verwachten
| Fase | Lampje | Status | Opmerking |
|---|---|---|---|
| Klaar | uit | Uit | Kan aan |
| Opwarmen | groen knipperend | Opwarmen | Ongeveer 7 minuten. Er komen al eerder vlammen, maar de vlamhoogte is nog niet regelbaar |
| Brandt | – | Brandt | Begint op stand 5, regelbaar 1–10 |
| Afkoelen | rood knipperend | Afkoelen | Kan meer dan een uur duren. Niet aan te zetten of bij te vullen |

Een automatisering op `sensor.<naam>_status` van `cooling` naar `off` is een handige manier om een melding te
krijgen als de haard weer gebruikt of bijgevuld kan worden.

Het protocol staat beschreven in [PROTOCOL.md](PROTOCOL.md) (Engels).
