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
| `sensor.<naam>_status` | Uit / Opwarmen / Brandt / Afkoelen / Onbekende fase |
| `sensor.<naam>_laatst_aangezet` | Wanneer de haard voor het laatst is aangezet (blijft staan als hij uit gaat) |
| `sensor.<naam>_brandstofniveau` | Brandstof in % (stappen van 10%) |
| `binary_sensor.<naam>_brandstof_bijna_op` | Aan bij 10% brandstof of minder |
| `sensor.<naam>_kamertemperatuur` | Kamertemperatuur in °C |
| `sensor.<naam>_luchtvochtigheid` | Luchtvochtigheid in % |
| `lock.<naam>_kinderslot` | Kinderslot op de haard: vergrendelen of ontgrendelen |
| `sensor.<naam>_fasecode` | Ruwe fasecode (diagnostisch) |

### Veiligheid
De haard kent alleen *toggle*- en *stap*-commando's: hetzelfde commando zet hem aan én uit. De integratie leest
daarom altijd eerst de status en stuurt alleen een commando als dat nodig is:
- aanzetten wordt geweigerd tijdens het afkoelen of als het kinderslot aan staat;
- aanzetten wordt ook geweigerd als de haard een onbekende fasecode meldt (mogelijk een storing); de code komt
  in het logboek zodat hij kan worden toegevoegd;
- na een aan/uit- of kinderslot-commando wordt 30 seconden geen tweede gestuurd tot de haard de nieuwe toestand
  meldt;
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
**Instellingen → Apparaten en diensten → Integratie toevoegen → Wild Flame.**

| Veld | Uitleg |
|---|---|
| IP-adres | Adres van de haard op zijn eigen wifi. Laat het op `192.168.4.1` staan, tenzij je het hebt veranderd. |

De integratie controleert direct of de haard bereikbaar is. Het apparaat heet *Wild Flame*; geef het op de
apparaatpagina een eigen naam (bijvoorbeeld "Haard") en laat Home Assistant de entiteit-ID's meeveranderen.

Is het adres veranderd? Kies bij de integratie **⋮ → Opnieuw configureren**; verwijderen is niet nodig.

## Wat je kunt verwachten
| Fase | Lampje | Status | Opmerking |
|---|---|---|---|
| Klaar | uit | Uit | Kan aan |
| Opwarmen | groen knipperend | Opwarmen | Ongeveer 7 minuten. Er komen al eerder vlammen, maar de vlamhoogte is nog niet regelbaar |
| Brandt | – | Brandt | Begint op stand 5, regelbaar 1–10 |
| Afkoelen | rood knipperend | Afkoelen | Kan meer dan een uur duren. Niet aan te zetten of bij te vullen |

## Voorbeelden
- Een melding als de haard weer gebruikt of bijgevuld kan worden: trigger op `sensor.<naam>_status` die van
  *Afkoelen* naar *Uit* gaat.
- Een herinnering om bij te vullen: trigger op `binary_sensor.<naam>_brandstof_bijna_op` die aan gaat.
- Zorgen dat de haard nooit de hele nacht brandt: een automatisering die `switch.<naam>` uitzet als hij
  bijvoorbeeld 4 uur aan staat (statustrigger met *voor*). Let op: als Home Assistant herstart, begint die
  wachttijd opnieuw.
- Zien hoe lang de haard al aan het opwarmen of afkoelen is: het tijdstip *laatst gewijzigd* van
  `sensor.<naam>_status`, te zien in het venster en de geschiedenis van die entiteit.
- De haard uit als iedereen weg is: een automatisering op je aanwezigheidsdetectie die `switch.<naam>` uitzet.

## Hoe vaak wordt de status bijgewerkt?
Home Assistant vraagt elke 5 seconden de status op, en direct na elk commando. Wat je op de haard zelf
of met de officiële app doet, zie je dus binnen een paar seconden terug.

## Bekende beperkingen
- De haard heeft alleen een eigen wifi; Home Assistant heeft een (tweede) wifi-verbinding daarmee nodig.
- De haard kent alleen wissel- en stapcommando's. Daarom wordt een commando geweigerd zolang een vorig
  aan/uit- of kinderslot-commando nog wordt verwerkt.
- De vlamhoogte is alleen regelbaar als de haard brandt, niet tijdens het opwarmen.
- Het brandstofniveau gaat in stappen van 10%.
- Alleen de Smart Fire A6 is getest. Andere Smart Fire-modellen werken waarschijnlijk hetzelfde; laat het weten.

## Problemen oplossen
- **"Kan de haard niet bereiken" bij het toevoegen, of alle entiteiten niet beschikbaar**: controleer of Home
  Assistant nog met het `WILDFLAME…`-wifi verbonden is (Instellingen → Systeem → Netwerk). De haard laat maar
  een paar wifi-apparaten toe; een telefoon of tablet ervan loskoppelen kan helpen.
- **"Onbekende fase"**: de haard meldt een fasecode die de integratie nog niet kent, mogelijk een storing.
  Aanzetten is dan geblokkeerd. Meld de code en wat de haard laat zien in een issue.
- Voeg bij een melding de diagnostiek toe: op de apparaatpagina **⋮ → Diagnostiek downloaden**.

## Verwijderen
1. **Instellingen → Apparaten en diensten → Wild Flame → ⋮ → Verwijderen.** Ook het opgeslagen tijdstip
   *laatst aangezet* wordt dan verwijderd.
2. Via HACS geïnstalleerd? Verwijder **Wild Flame** dan ook in HACS en herstart Home Assistant.

Het protocol staat beschreven in [PROTOCOL.md](PROTOCOL.md) (Engels).
