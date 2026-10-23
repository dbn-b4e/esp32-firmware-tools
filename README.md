# ESP32 firmware tools

Outils Python communs : compilation Arduino ESP32, LittleFS, rapports de build,
contrôle des bibliothèques, flash USB et génération/vérification OTA full/diff. Premier utilisateur : B4E.
SxS est un projet figé et n'utilise pas ce dépôt.

```text
esp32-firmware-tools/
├── build.py           # lanceur de compilation pour un projet choisi
├── esp32_tools/       # moteur Arduino, LittleFS, flash et contrôles
└── ota/               # générateurs/vérificateurs full et différentiels
```

Le projet firmware conserve son `build.py` et `build-config.json`, puis référence
ce dépôt comme sous-module Git à un commit précis. Le moteur ne contient aucun
firmware, secret ou réglage réseau. Python >= 3.10, Arduino CLI et `requests`
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
B4E (base `bd707ec`, auteur David Baldwin / B4E). Les modules project, partitions
et arduino séparent configuration, politiques et découverte des outils.

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
