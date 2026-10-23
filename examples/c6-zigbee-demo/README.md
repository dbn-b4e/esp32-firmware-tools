# Exemple C6 : BOOT, LED et température simulée

Petit firmware Zigbee autonome, sans WiFi, MQTT ni secrets. Il utilise le core
Arduino ESP32 3.3.4 standard, sans carte custom et sans patch Zigbee global.
Le convertisseur expose une sortie, une entrée et une mesure dans Z2M puis HA.

## Matériel et endpoints

| Fonction | Broche | Endpoint | Propriété Z2M |
|---|---|---|---|
| LED discrète ON/OFF | GPIO2, active HIGH par défaut | 10 `led` | `state_led` |
| BOOT | GPIO9, pull-up, appui LOW | 20 `boot` | `pressed_boot` |
| Température simulée | Aucune | 30 `simulated` | `temperature_simulated` |

Adapter `sketch/board_config.h` au **schéma de la carte réelle** avant flash :
certaines cartes utilisent une LED RGB adressable, que cette sortie ne pilote
pas. Une LED externe nécessite sa résistance série. GPIO12/13 restent réservés
à l’USB ; les assertions refusent leur affectation. Ne pas modifier GPIO9 avec
un montage qui perturberait le démarrage. Aucun relais n’est commandé ici.

BOOT est anti-rebondé pendant 30 ms. L’état est envoyé après changement avec
limitation des tentatives à une seconde et rappel toutes les 30 secondes ; des
appuis très brefs ne sont donc pas une source garantie d’événements. La mesure
simulée varie en triangle de 20 à 25 °C, par pas de 0,1 °C toutes les 5 secondes.
C’est une démonstration d’état binaire, pas un compteur d’appuis.

## Compiler

Depuis la racine des outils, après installation des prérequis du README racine :

```sh
python3 examples/c6-zigbee-demo/build.py --info
python3 examples/c6-zigbee-demo/build.py --check-environment
python3 examples/c6-zigbee-demo/build.py --check-libraries
python3 examples/c6-zigbee-demo/build.py --build
```

Depuis le dossier de l’exemple, utiliser simplement `python3 build.py --build`.
`build-config.json` déclare le core, la carte et ses options ;
`sketch/version.h` porte la version uint32. Les binaires générés vont dans
`firmware/` et le travail dans `build/`. Aucun flash avec `--build`.

Après identification physique de la carte et confirmation du port :

```sh
python3 build.py --flash --port PORT_CONFIRME
```

Cette opération remplace le programme et les métadonnées de boot. Utiliser une
carte de test dédiée ; ne pas remplacer un firmware B4E en service pour essayer
cet exemple. L’exemple ne possède ni client OTA ni effacement Zigbee automatique.
Une association existante est conservée ; un long appui BOOT ne fait pas de
factory reset. **Changer de modèle ou d’endpoints n’est pas une simple mise à
jour compatible** : les enregistrements de reporting persistants de l’ancien
FW peuvent référencer des attributs absents et faire planter la pile Zigbee.
Ce cas a été reproduit en remplaçant B4E par cet exemple sur la carte de test.

Pour migrer entre ces modèles, sauvegarder la flash complète puis réinitialiser
explicitement le stockage Zigbee local, et prévoir un nouvel appairage/interview
Z2M. Sur le layout **exact de cet exemple seulement**, `zb_storage` est la région
`0x3EB000` de taille `0x4000`. Son effacement USB a supprimé le crash reproduit.
Il supprime l’association et les données réseau Zigbee locales ; il n’est pas
exécuté automatiquement par `build.py` ou par le FW. Ne pas effacer NVS, FS ou
la flash entière pour contourner ce problème. Sur une carte déjà enregistrée
par Z2M, traiter son ancienne identité avant de la réutiliser sous un autre
modèle, avec accord explicite pour les opérations sur cette installation.

## Générer le convertisseur depuis le FW

Dans la console série 115200 : `help`, `status`, `describe`.
`describe` répond `Z2M_DESCRIPTOR {JSON}`. La table et les constantes de
`sketch/descriptor.h` alimentent à la fois les vrais objets Zigbee et cet export.
Le test natif exécute ce header, valide le JSON et compare les fichiers dérivés
archivés `descriptor.example.json` et `converter.mjs`.

Depuis la racine des outils, export hors ligne disponible immédiatement :

```sh
python3 z2m/converter.py validate --input examples/c6-zigbee-demo/descriptor.example.json
python3 z2m/converter.py generate --input examples/c6-zigbee-demo/descriptor.example.json --output demo.mjs
```

Pour récupérer l’export de la carte plutôt que le snapshot :

```sh
python3 -m pip install -r z2m/requirements-serial.txt
python3 z2m/converter.py capture --port PORT_CONFIRME --output capabilities.json
python3 z2m/converter.py generate --input capabilities.json --output demo.mjs
```

Fermer les autres consoles avant capture ; l’ouverture USB peut provoquer un
reset suivant la carte. Voir [le contrat générique](../../z2m/README.md) pour
adapter un autre firmware sans dépendre d’Arduino.

## Z2M et Home Assistant

Installer `demo.mjs` comme convertisseur externe dans votre Z2M selon son guide
officiel. Activer l’autorisation JS externe si nécessaire. Sur une carte neuve,
autoriser l’appairage dans Z2M puis démarrer la carte à proximité ; attendre
l’interview et vérifier modèle `C6-TOOLS-DEMO`, fabricant `Example`, EP10/20/30.
Ces actions sur une installation de production doivent être planifiées.

Dans Z2M, la sortie `state_led` accepte ON/OFF/TOGGLE ; BOOT est en lecture seule.
Exemples de messages sur `zigbee2mqtt/NOM_APPAREIL/set` :

```json
{"state_led":"ON"}
```

```json
{"state_led":"OFF"}
```

```json
{"state_led":"TOGGLE"}
```

Le topic d’état contient par exemple
`{"state_led":"ON","pressed_boot":false,"temperature_simulated":21.3}`.
Avec la découverte MQTT HA activée, retrouver le switch LED, le binary sensor
BOOT et le sensor de température dans l’appareil MQTT correspondant. Leurs
entity_id dépendent du nom donné dans votre HA ; ne pas copier un nom supposé.

Dans l’éditeur d’automatisation HA, un exemple simple : déclencheur **changement
d’état de BOOT de off vers on**, action **basculer le switch LED**. Ne pas
utiliser « tout message MQTT reçu » : les rappels d’état et messages retenus
pourraient faire basculer la LED sans nouvel appui.

## Architecture et vérification

`loop()` ne gère que la console et son délai. Une tâche applicative lit BOOT,
écrit la LED et met à jour les mesures. Le callback Zigbee stocke seulement la
consigne LED atomique ; la tâche applicative est l’unique auteur du GPIO après
setup. Les snapshots de console sont atomiques ; les buffers de console et
compteurs de debounce restent locaux à leur tâche.

Le champ console `zigbee` reflète le drapeau « associé/restauré » du SDK Arduino,
**pas un test de liaison en direct**. Dans le core 3.3.4, `started/connected`
reposent sur des booléens ordinaires mis à jour par la tâche SDK : cette limite
du SDK n’est pas corrigée par les atomiques de l’application. Le statut ne doit
pas être utilisé comme watchdog de sécurité. Les appels ZCL employés passent
par les verrous du SDK ; les échecs de reporting BOOT sont retentés. La console
affiche la température simulée locale, pas un accusé de réception du coordinateur.

Vérifié : compilation réelle C6 sur Mac, export du header C++ exécuté sur hôte,
validation JSON, génération déterministe et exécution des converters avec la
vraie bibliothèque Z2M verrouillée. Le 23 octobre 2026, flash USB physique puis
capture `describe` réussie sur ESP32-C6 : le JSON réel et le `.mjs` produit sont
identiques aux snapshots testés. Le démarrage a nécessité la migration explicite
du stockage Zigbee décrite plus haut. Aucun changement HA/Z2M n’a été effectué.

Restent à vérifier physiquement : brochage/LED, appui réel, nouvel appairage,
reporting, reconnexion et comportement après coupure. La CI et la console ne
remplacent pas ces tests avec le coordinateur.

Si la LED ne s’allume pas, contrôler le brochage, active LOW et type de LED.
Si le convertisseur ne charge pas, vérifier autorisation JS externe et version
modernExtend. Si l’appareil reste non supporté, comparer son identité et ses
clusters réels au JSON ; ne pas élargir le fingerprint pour masquer un écart.
