# Du firmware au convertisseur Z2M

Le générateur consomme un JSON de capacités, indépendant du langage et du
microcontrôleur. Il ne lit pas le C++ et ne décompile pas un binaire. Le FW doit
exporter ce contrat, ou le projet doit le produire depuis les mêmes données que
sa déclaration d’endpoints. Ne pas recopier à la main une configuration privée.

## Circuit complet

1. Le firmware enregistre ses endpoints et clusters Zigbee.
2. La commande console `describe` exporte leurs capacités publiques.
3. `capture` récupère le JSON ; un export fichier est également accepté.
4. `validate` vérifie le contrat ; `generate` crée le `.mjs` déterministe.
5. Installer le convertisseur dans Z2M et vérifier l’interview réelle.
6. HA reçoit ensuite les entités par la découverte MQTT de Z2M, si activée.

```sh
python3 z2m/converter.py validate --input capabilities.json
python3 z2m/converter.py generate --input capabilities.json --output device.mjs
# Remplacement volontaire d’un fichier déjà généré :
python3 z2m/converter.py generate --input capabilities.json --output device.mjs --force
```

Un fichier existant est protégé par défaut ; `--force` le remplace atomiquement.
Entrée et sortie identiques et liens symboliques de sortie sont refusés.
Utiliser des dossiers locaux de confiance ; ces gardes ne visent pas un
adversaire modifiant simultanément les répertoires parents.

## Contrat schema_version = 1

Exemple minimal d’une entrée BOOT :

```json
{
  "schema_version": 1,
  "device": {
    "model": "MY-DEMO",
    "manufacturer": "Example",
    "description": "BOOT input",
    "firmware_version": 65536
  },
  "ota": false,
  "endpoints": [{
    "id": 20,
    "name": "boot",
    "clusters": {"input": [0, 3, 15], "output": []},
    "features": [{"type": "binary_input", "property": "pressed"}]
  }]
}
```

`input` signifie **serveur Zigbee local**, pas entrée électrique ; `output`
signifie client. L’identité doit correspondre exactement aux attributs Basic
`modelIdentifier` et `manufacturerName` de la carte. Le convertisseur utilise
ces deux valeurs comme fingerprint. `firmware_version` est informatif ; il ne
sélectionne ni un tag Git ni un binaire.

| Champ | Règles |
|---|---|
| `schema_version` | Entier exact 1 |
| `device.model`, `manufacturer` | Texte non vide, au plus 32 octets UTF-8 |
| `device.description` | Texte non vide, au plus 512 octets |
| `device.firmware_version` | Optionnel : uint32 ou texte de 64 octets maximum |
| `ota` | Booléen ; true exige un cluster client OTA 25 |
| `endpoints` | 1 à 32 ; IDs entiers uniques 1 à 240, noms uniques |
| `name`, propriété binaire | `[a-z][a-z0-9_]{0,31}` |
| `clusters.input/output` | Listes d’entiers uint16 uniques, 64 maximum chacune |
| `features` | 1 à 4 types distincts par endpoint |

Les propriétés inconnues, clés JSON dupliquées et fichiers dépassant 64 Kio sont
refusés. Les clusters serveur sans représentation prise en charge sont refusés,
hormis Basic 0, Identify 3, Groups 4 et Scenes 5. Le tool ne prétend donc pas
avoir généré un support complet pour un cluster propriétaire inconnu.

| `type` | Cluster serveur requis | Propriété Z2M/HA | Commande |
|---|---|---|---|
| `on_off` | 6 genOnOff | `state_NOM` : ON/OFF | SET et GET |
| `binary_input` | 15 genBinaryInput | `PROPRIETE_NOM` : booléen | GET, lecture seule |
| `temperature` | 1026 msTemperatureMeasurement | `temperature_NOM` : °C | GET |
| `humidity` | 1029 msRelativeHumidity | `humidity_NOM` : % | GET |

`binary_input.property` vaut `state` par défaut ; choisir `pressed` pour un
bouton. Les collisions de noms finaux sont refusées, y compris entre endpoints.
Le `property` personnalisé n’est accepté que pour l’entrée binaire.

`reporting` est optionnel pour binaire/température/humidité :
`{"min":5,"max":60,"change":10}`. Les intervalles sont des secondes,
`0 <= min <= max <= 65534`, avec max au moins 1. `change` est en unités ZCL :
0/1 pour le booléen, centièmes de °C ou centièmes de %. Il va de 0 à 32767 pour
les mesures. Défauts : binaire 0/60/1, température 5/60/10, humidité 5/60/100.
ON/OFF utilise le reporting standard modernExtend, sans override dans ce schéma.

Le générateur encode les textes comme des données JSON, sans interpolation de
code exécutable. Il faut néanmoins choisir des libellés publics : cette
protection n’empêche pas un humain d’écrire une donnée confidentielle dans
`description` ou `model`. Aucun SSID, mot de passe, MAC, IP ou dump de préférences
ne doit être exporté. `ota: true` déclare un client existant, il ne l’installe pas.

## Transport série optionnel

```sh
python3 -m pip install -r z2m/requirements-serial.txt
python3 z2m/converter.py capture --port PORT_CONFIRME --baud 115200 --timeout 15 --output capabilities.json
```

Le FW reçoit `describe\n` et répond en UTF-8 sur **une ligne** :

```text
Z2M_DESCRIPTOR {"schema_version":1,...}
```

Le préfixe est suivi d’un JSON complet et d’un LF ou CRLF. Les autres lignes
sont ignorées et ne sont jamais enregistrées. Les lignes trop longues sont
écartées. Une réponse invalide est ignorée jusqu’au timeout ; l’absence de
réponse valide échoue sans sauvegarder les logs. La requête est répétée toutes
les deux secondes. Les lectures et écritures sont bornées ; le délai total
peut dépasser légèrement le timeout demandé à cause d’une opération I/O en
cours. Le CLI accepte un timeout de 1 à 120 secondes.

DTR/RTS sont désactivés avant ouverture, mais un reset USB reste possible selon
la carte et son driver. Fermer tout autre terminal série ; sélectionner et
confirmer le port avant utilisation sur un appareil en service.

Le cœur de génération n’exige ni pyserial, ni Node, ni Arduino. Pour une console
WebSocket ou HTTP, exporter le même JSON dans un fichier ; ces transports ne
sont pas encore implémentés dans le CLI.

## Installation dans Z2M

Utiliser Settings → Dev console → External converters, ou le dossier
`external_converters` suivant la version Z2M. Vérifier que l’exécution JS externe
est autorisée (`advanced.enable_external_js`) ; changer ce réglage peut demander
un redémarrage. L’ajout/rechargement d’un convertisseur est distinct de cette
configuration. Aucune modification de votre Z2M n’est faite par le générateur.

Consulter [le guide officiel](https://www.zigbee2mqtt.io/advanced/more/external_converters.html)
et [les réglages Z2M](https://www.zigbee2mqtt.io/guide/configuration/all-settings.html).
L’outil intégré « Generate external definition » de Z2M reste utile pour
comparer l’interview et les clusters réels ; notre descriptif apporte les noms
sémantiques, types d’accès et choix de reporting du firmware.

L’API modernExtend est vérifiée avec la version verrouillée
`zigbee-herdsman-converters@26.115.1`. Vérifier la version embarquée par une autre
installation Z2M si une erreur de chargement apparaît. Le générateur ne contacte
pas le coordinateur pour vérifier que le FW respecte son descriptif.
