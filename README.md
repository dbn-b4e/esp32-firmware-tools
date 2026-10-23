# ESP32 firmware tools

Outils Python communs : compilation Arduino ESP32, LittleFS, rapports de build,
contrôle des bibliothèques, flash USB et génération/vérification OTA full/diff. Premier utilisateur : B4E.
SxS est un projet figé et n'utilise pas ce dépôt.

```text
esp32-firmware-tools/
├── build.py           # lanceur de compilation pour un projet choisi
├── arduino/           # moteur Arduino, LittleFS, flash et contrôles
├── common/            # utilitaires indépendants du compilateur
├── ota/               # générateurs/vérificateurs full et différentiels
├── z2m/               # descriptif FW JSON → convertisseur .mjs
└── examples/          # démonstration C6 indépendante
```

Le lanceur racine appelle actuellement le backend Arduino ; aucun backend
ESP-IDF ou PlatformIO n’est encore fourni.

Le projet firmware conserve son `build.py` et `build-config.json`, puis référence
ce dépôt comme sous-module Git à un commit précis. Le moteur ne contient aucun secret ou réglage réseau ; un firmware de
démonstration autonome est fourni dans `examples/`. Python >= 3.10, Arduino CLI et `requests`
sont nécessaires ; les outils esptool/mklittlefs viennent du core Arduino choisi.
Aucune installation n'est faite automatiquement.

```sh
python3 build.py --project /chemin/du/projet --help
python3 build.py --project /chemin/du/projet --info
python3 build.py --project /chemin/du/projet --check-environment
python3 build.py --project /chemin/du/projet --check-libraries
python3 build.py --project /chemin/du/projet --build
```

Le projet appelle normalement ces commandes via son propre `python3 build.py`.
`--build` construit aussi LittleFS si `data/` existe. `--flash --port PORT` et
`--littlefs --port PORT` sont les écritures USB explicites ; aucun flash implicite
avec `--build`. `--auto` combine compilation et écritures explicites, avec port
obligatoire. Effacement et nettoyage hérités restent désactivés.

Configuration : schema_version=1, project, core{id,version exacte},
board{id,options}, chip, bootloader_offset (`0x0` ou `0x1000`),
version{macro uint32}, upload_baud et paths{sketch,partitions,version_header,
requirements,build,firmware}. Le CSV est celui du sketch ; chemins relatifs
confinés au projet. Cette première extraction exige une partition `app0/ota_0`
et utilise `littlefs` pour le système de fichiers.

La clé optionnelle `policy` désigne un module Python **de confiance**, appartenant
au projet. Il ajoute ses contraintes via validate_config(root,config),
check_environment(root,config,cores), validate_layout(csv_path), et
validate_device(esptool_command,port,csv_path,workdir,check_partition).
La politique B4E conserve ses contrôles exacts de partitions et de copie Zigbee.

Le moteur de build/rapports/gestion des bibliothèques est extrait du dépôt
B4E (base `bd707ec`, auteur David Baldwin / B4E). Les modules `arduino/project.py`, `arduino/partitions.py` et
`arduino/toolchain.py` séparent configuration, politiques et découverte des
outils Arduino. `common/console.py` reste indépendant du compilateur.

Validation : `python3 -m unittest discover -s tests -v`.
Compilation Arduino réelle B4E validée sur Mac uniquement ; aucun flash Linux
ou Windows dans ce lot. La CI exécute les tests CLI sous macOS, Linux et Windows
avec Python 3.10/3.13. Les tests couvrent notamment suffixe `.exe`, espaces et résolution
par les propriétés Arduino, sans chemins Mac codés en dur.

## OTA : modules autonomes dans ce même dépôt

Le contenu de l’ancien dépôt esp32C6-OTA-Builder est intégré dans `ota/`, avec
historique et licences. Ce dossier n’est pas un sous-module supplémentaire.

```sh
python3 ota/zigbee_ota_generator.py --help
python3 ota/delta_ota.py --help
python3 -m pip install -r requirements-delta.txt  # seulement pour les deltas
```

Le full nécessite uniquement la bibliothèque standard Python ; le delta utilise
les versions épinglées de detools/esptool. Les commandes de création et de
vérification complètes sont dans [le guide OTA](ota/readme.md).
Le contrat différentiel conserve son enveloppe de 128 octets : il exige un
firmware compatible et ne devient pas le format Zigbee natif Espressif par ce
rangement. Aucun appareil n’est contacté pour générer ou vérifier les fichiers.

Tests OTA : depuis `ota/`, `python3 -m unittest discover -s tests -v`.
La CI exécute les deux suites sur les six combinaisons OS/Python.

Restent à réaliser : sélection Git de tags pour compiler les firmwares,
installation de cartes custom et interface Qt.

Le CLI lance un processus neuf par invocation et sélectionne un seul projet.
Ne pas importer le moteur pour piloter plusieurs projets dans des threads :
contexte, cwd et cache des propriétés sont propres au processus. Une seule
compilation à la fois par projet (pas encore de verrou inter-processus).

Les commandes historiques de maintenance des bibliothèques et routines internes
héritées sont conservées, mais n'ont pas toutes été revalidées dans ce premier
lot. Les chemins désactivés ne constituent pas une API générique supportée.
Un échec/timeout de découverte Arduino arrête la chaîne ; certaines erreurs de
réponse CLI peuvent encore afficher un traceback au lieu d'un message court.


## Démarrer avec l’exemple C6

L’exemple utilise la carte **standard** `esp32:esp32:esp32c6` et le core
**3.3.4**, sans carte custom ni patch de la bibliothèque Zigbee globale.
Les options `ZigbeeMode=ed`, `PartitionScheme=custom`, `CDCOnBoot=cdc`,
`FlashSize=4M` sont dans
[build-config.json](examples/c6-zigbee-demo/build-config.json).
Le CSV de partitions et la version sont dans son dossier `sketch/`.
Sur une machine neuve, les commandes CLI correspondantes sont :

```sh
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.4 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
```

Elles installent le core localement ; le lanceur de build ne les exécute pas
implicitement.

Installer Python >= 3.10 et Arduino CLI selon
[la documentation officielle](https://arduino.github.io/arduino-cli/latest/installation/).
Sur une nouvelle machine, déclarer l’index ESP32 officiel, actualiser l’index,
puis installer exactement `esp32:esp32@3.3.4` ; voir
[le guide Espressif](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html).
Ne pas changer un core utilisé par un autre projet sans vérifier ses contraintes.
Le tool contrôle la version installée et refuse un décalage.

macOS/Linux, depuis la racine des outils :

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python examples/c6-zigbee-demo/build.py --info
.venv/bin/python examples/c6-zigbee-demo/build.py --check-environment
.venv/bin/python examples/c6-zigbee-demo/build.py --check-libraries
.venv/bin/python examples/c6-zigbee-demo/build.py --build
```

Windows PowerShell :

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe examples/c6-zigbee-demo/build.py --info
.venv\Scripts\python.exe examples/c6-zigbee-demo/build.py --check-environment
.venv\Scripts\python.exe examples/c6-zigbee-demo/build.py --check-libraries
.venv\Scripts\python.exe examples/c6-zigbee-demo/build.py --build
```

`Zigbee==3.3.4` est fourni par le core ; ne pas installer une autre copie globale.
Les sorties sont sous `examples/c6-zigbee-demo/build/` et `firmware/`, ignorées
par Git. L’application s’appelle `sketch.ino.bin` ; les fichiers bootloader,
partitions et merged ont des rôles différents. Archiver les binaires exacts de
chaque release : ces dossiers de travail sont réutilisés au prochain build.
Le log horodaté précise les commandes et bibliothèques réellement utilisées.

Le [guide de l’exemple](examples/c6-zigbee-demo/README.md) explique le brochage,
les trois endpoints, l’installation du convertisseur et les manipulations HA.
Le flash USB et l’export `describe` sont validés sur C6. L’appairage et les
manipulations Zigbee restent à vérifier. Changer de modèle/endpoints peut exiger
une migration explicite du stockage Zigbee : voir le guide de l’exemple.

## Intégrer les outils à son propre firmware

Un projet conserve son Git et **un seul sous-module**, fixé à un commit :

```sh
git submodule add https://github.com/dbn-b4e/esp32-firmware-tools.git tools/esp32-firmware-tools
git -C tools/esp32-firmware-tools checkout COMMIT_VALIDE
git add .gitmodules tools/esp32-firmware-tools
git commit -m "Pin shared firmware tools"
```

Pour récupérer un projet existant : `git clone --recurse-submodules URL_PROJET` ;
pour une copie existante : `git submodule update --init --recursive`.
Une mise à jour est explicite : choisir le nouveau commit du sous-module,
compiler/tester, puis commiter sa référence dans le projet parent.
Les dossiers `arduino/`, `ota/`, `z2m/` appartiennent au même Git d’outils.

Wrapper minimal `build.py` à la racine du projet :

```python
import subprocess
import sys
from pathlib import Path
root = Path(__file__).resolve().parent
raise SystemExit(subprocess.call([
    sys.executable, str(root / "tools/esp32-firmware-tools/build.py"),
    "--project", str(root), *sys.argv[1:],
]))
```

Copier le `build-config.json` de l’exemple et adapter ses valeurs ; les noms de
champs sont le contrat commun. `project` est le libellé ; `core.version` est
exact ; `board.options` fournit les valeurs Arduino sans les coder dans le
moteur. `version.macro` désigne une définition numérique uint32 unique dans
`paths.version_header` (affichage `major.minor.patch` selon les octets 16/8/0).
`paths.requirements` contient les bibliothèques et contraintes de versions ;
`paths.build` et `paths.firmware` désignent les sorties. `upload_baud` concerne
le flash, pas la console. Tous les chemins sont relatifs à la racine du projet.
La partition CSV doit être `partitions.csv` dans le sketch compilé. Le backend
actuel impose `PartitionScheme=custom`, `app0/ota_0`, `otadata` et le layout
compatible avec ses contrôles ; toutes les cartes ESP32 ne sont pas validées.

Une politique optionnelle est du **code Python exécuté localement**, pas une
configuration inerte : n’ouvrir que des projets de confiance. Ses hooks sont
listés plus haut ; elle conserve les contrôles particuliers hors du moteur
commun. L’exemple n’a pas de politique. B4E garde sa politique de sécurité et
son packaging OTA dans son propre dépôt.

## Commandes et effets

| Commande du projet | Effet |
|---|---|
| `--info`, `--help` | Afficher configuration/aide |
| `--check-environment` | Lire core, partitions, version et politique |
| `--check-libraries` | Contrôler les dépendances installées |
| `--build` | Compiler l’application et aussi LittleFS si `sketch/data/` existe |
| `--build-littlefs` | Construire l’image FS sans l’écrire |
| `--flash --port PORT` | Écrire les composants firmware et métadonnées de boot après contrôles |
| `--littlefs --port PORT` | Remplacer le contenu LittleFS après contrôles |
| `--auto --port PORT` | Compiler puis écrire firmware et FS disponible |
| `--verify --port PORT` | Lire la flash pour comparaison avec l’image locale |
| `--erase`, `--clean`, `--clean-all` | Chemins destructifs désactivés |

Les contrôles de taille, partitions et politique précèdent l’écriture ; ils ne
remplacent pas l’identification de la carte et du port. Les commandes héritées
`--sync-libraries`, `--update-libraries`, `--auto-update` peuvent modifier les
bibliothèques de la machine : elles ne font pas partie du chemin reproductible
recommandé. `--silent` ne constitue pas une autorisation de déploiement.
`--ota` est une extension du wrapper B4E, pas une option du moteur générique.

## Convertisseur Z2M à partir du firmware

Le firmware publie un **descriptif de capacités versionné**, puis le générateur
produit du JavaScript ESM utilisant les modernExtend officiels de Z2M.
Le descriptif contient identité, endpoints, clusters et fonctions ; jamais un
dump de configuration. Aucune dépendance à Arduino, au C6 ou à OZ pour la
validation/génération. Aucun accès HA, MQTT ou réseau n’est nécessaire.

```sh
python3 z2m/converter.py validate --input examples/c6-zigbee-demo/descriptor.example.json
python3 z2m/converter.py generate --input examples/c6-zigbee-demo/descriptor.example.json --output mon-convertisseur.mjs
```

Pour un FW compatible en fonctionnement : envoyer `describe` sur sa console et
récupérer la ligne `Z2M_DESCRIPTOR {…}`. L’adaptateur série optionnel automatise
cela, avec port explicite et délai borné :

```sh
python3 -m pip install -r z2m/requirements-serial.txt
python3 z2m/converter.py capture --port PORT_CONFIRME --output capabilities.json
python3 z2m/converter.py generate --input capabilities.json --output mon-convertisseur.mjs
```

L’ouverture USB peut redémarrer une carte selon son circuit/driver, même avec
DTR/RTS désactivés ; ne pas ouvrir automatiquement une carte en service.
Le firmware doit implémenter le contrat : le tool ne devine ni un `.bin`
quelconque ni les intentions d’un code C++. Pour l’exemple, la même table C++
alimente les endpoints et l’export ; un test natif exécute ce header et compare
son export et le `.mjs` archivés. Voir [le contrat complet](z2m/README.md).

## Validation, publication et limites

```sh
python3 -m unittest discover -s tests -v
# Depuis ota/, avec les dépendances delta installées :
python3 -m unittest discover -s tests -v
# Tests du JavaScript généré avec la vraie bibliothèque Z2M :
npm ci --prefix tests/z2m-runtime --ignore-scripts --no-audit --no-fund
npm test --prefix tests/z2m-runtime
```

Les tests du générateur n’ont pas besoin de Node ; les tests runtime JS utilisent
`zigbee-herdsman-converters@26.115.1`, verrouillé dans package-lock.json. Node
22/24 sont testés en CI. Le test natif du header nécessite un compilateur C++ ;
il est ignoré explicitement lorsqu’il n’est pas disponible. Les tests Python
couvrent les trois OS, mais ne prouvent pas le flash USB sur ces plateformes.
La compilation réelle du C6 et celle du projet B4E sont vérifiées sur macOS.

Les quatre fonctions actuellement prises en charge sont ON/OFF, entrée binaire,
température et humidité. Les clusters custom, scènes avancées, thermostats,
interview Z2M comme source et découverte automatique de code restent hors scope.
L’exemple n’embarque aucun client OTA. Les scripts OTA et le générateur Z2M sont
indépendants : annoncer `ota: true` ne crée pas un décodeur dans le firmware.

La génération différentielle ne modifie pas le core Arduino. Le décodeur doit
être intégré **dans le projet firmware** selon le contrat documenté dans `ota/`.
Le format différentiel B4E utilise une enveloppe de 128 octets, un en-tête
Espressif de 64 octets et un patch detools ; ce n’est pas un client delta natif
universel fourni par Arduino 3.3.4. Le full reste disponible pour un appareil
qui accepte son format. Compiler un tag Git puis fabriquer ses OTA reste deux
étapes explicites ; aucun orchestrateur de tags, Qt ou installation de cartes
custom n’est implémenté.

Voir [l’audit de publication](docs/PUBLICATION.md), [LICENSE](LICENSE) et
[NOTICE.md](NOTICE.md). Le nom et l’adresse d’auteur présents dans l’historique
Git sont des métadonnées publiques. Les contrôles recherchent les secrets et
artefacts privés ; ils ne garantissent pas l’absence de toute information
personnelle ou de toute vulnérabilité future.
