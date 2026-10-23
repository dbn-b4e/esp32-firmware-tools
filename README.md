# ESP32 firmware tools

Moteur Python commun de compilation Arduino ESP32, LittleFS, rapports de build,
contrôle des bibliothèques et flash USB explicite. Premier utilisateur : B4E.
SxS est un projet figé et n'utilise pas ce dépôt.

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
Mac testé par compilation réelle B4E ; Linux/Windows ne sont pas encore validés
sur machine. Les tests couvrent notamment suffixe `.exe`, espaces et résolution
par les propriétés Arduino, sans chemins Mac codés en dur.

Hors de ce premier lot : génération OTA (dépôt esp32C6-OTA-Builder), sélection
Git de tags, installation de cartes custom et interface Qt.
