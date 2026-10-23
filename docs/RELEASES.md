# Compiler un tag et fabriquer ses releases

Le point d’entrée reste **build.py**. Le moteur compile la source d’un tag Git
local dans une copie isolée, puis fabrique une archive vérifiée. Le checkout
courant, sa branche et les archives existantes ne sont pas modifiés. Aucun flash,
MQTT, appel HA/Z2M, installation de core ou téléchargement implicite de Git.

## Commandes

Depuis un projet dont le wrapper utilise une version récente des outils :

```sh
# Afficher la sélection, la version du header, les paramètres et destinations.
python3 build.py release plan --ref v1.2.0

# Compiler le tag et archiver ses sorties, dont le full si configuré.
python3 build.py release build --ref v1.2.0

# Full et deux deltas directs, depuis les binaires exacts des anciennes releases.
python3 build.py release build --ref v1.2.0 \
  --base-release build/releases/mon-projet/v1.0.0 \
  --base-release build/releases/mon-projet/v1.1.0

# Contrôle autonome d’une archive et reconstruction de tous ses deltas.
python3 build.py release verify --archive build/releases/mon-projet/v1.2.0
```

Depuis le dépôt d’outils, ajouter `--project /chemin/du/projet` **avant** `release`.
Sous Windows utiliser `py -3` ou le Python du venv, avec les mêmes arguments ;
les chemins contenant des espaces doivent être cités. Les chemins relatifs
des bases et de `--legacy-base-profile` sont résolus depuis le projet, comme
`--output` et `--archive`, indépendamment du cwd du wrapper. Les appels internes
utilisent des listes d’arguments, sans shell.

`--output CHEMIN_RELATIF` choisit une autre destination dans le projet. Elle doit
être ignorée par Git et ne pas exister. Pas de `--force` : une release existante
est une base potentiellement installée, pas un dossier de staging à recycler.
Le défaut est `build/releases/NOM/vMAJOR.MINOR.PATCH`. Si le projet n’ignore pas
encore `build/`, l’ajouter à son `.gitignore` avant de lancer le CLI.

`plan` ne compile rien et ne crée aucun dossier. Il vérifie aussi les bases
fournies ; leur validation ESP peut demander les dépendances delta. `verify`
n’exige ni source Git ni Arduino installé pour une archive déjà produite, mais
les dépendances delta sont nécessaires si elle contient ce profil/des deltas.

## Préparer son projet

Commiter `build-config.json`, les sources et un `release-config.json`, puis créer
un tag sur ce commit. La version vient de la macro uint32 déclarée dans le
build-config du **tag**, pas du fichier sale dans le checkout courant. Un nom
de tag `v1.2.0` ou `1.2` doit correspondre à cette version (1.2 équivaut à 1.2.0).
Les autres noms de tags restent possibles ; ils ne remplacent jamais la macro.
`HEAD`, les branches, les expressions Git et les refs distantes sont refusés.

Configuration sans packaging OTA, comme le démonstrateur C6 sans client OTA :

```json
{"schema_version":1,"name":"mon-projet","local_inputs":[]}
```

Le build est alors archivé et vérifié sans prétendre fournir une mise à jour
consommable par cet appareil. Pour un firmware possédant un client OTA compatible :

```json
{
  "schema_version": 1,
  "name": "mon-projet",
  "local_inputs": ["sketch/config.h"],
  "full_ota": {
    "manufacturer_code": 4169,
    "image_type": 1,
    "header_string": "MY_DEVICE_V1",
    "stack_version": 2,
    "min_hardware_version": 1,
    "max_hardware_version": 1,
    "espressif_compatible": true
  },
  "delta_profile": "ota-profile.json"
}
```

Les valeurs OTA ci-dessus sont illustratives. Les adapter au client réellement
installé. `full_ota` est optionnel et reprend les paramètres du builder full ;
tous les champs montrés sont explicites, `file_version` vient du header compilé.
`delta_profile` est optionnel ; sans lui, aucun `--base-release` n’est accepté.
Voir [le profil delta](../ota/examples/esp32c6-profile.json) et
[le contrat du décodeur](../ota/docs/delta-format.md). Le profil doit correspondre
à l’identité full, au modèle, au slot et au décodeur ESP32-C6 embarqué. Ajouter un
profil dans Git n’ajoute pas le décodeur au firmware.

`local_inputs` déclare les seuls fichiers privés copiés depuis le checkout local
vers la source isolée. Chaque fichier doit être présent, ignoré par Git, relatif
au projet et ne pas remplacer de source du tag. Son chemin logique, sa taille
et son SHA256 sont enregistrés ; son contenu n’est pas écrit dans le manifeste.
Une modification entre préparation et copie, ou dans la copie pendant le build,
fait échouer la release. Ne pas ajouter des dossiers entiers ou un fichier
contenant des secrets à Git pour faire passer la vérification.

Les fichiers de configuration/politique du tag sont du code/configuration de
confiance. Cette isolation protège le checkout et la traçabilité ; ce n’est pas
une sandbox pour compiler un dépôt malveillant.

## Tags, sous-modules et outils

Le tag est résolu en commit avant le build. `git archive` exporte ses objets ;
les modifications non commitées ne sont pas copiées. Les attributs d’export Git
s’appliquent : ne pas marquer les sources nécessaires `export-ignore`.
Les liens symboliques et hardlinks dans l’export sont refusés.

Les sous-modules sont exportés à leur **gitlink exact**, récursivement, depuis
les bases d’objets locales. Un checkout sale d’un sous-module ne remplace pas
cette source. Si les objets manquent, initialiser/récupérer explicitement le
sous-module avant de réessayer ; le tool ne fait pas de fetch automatique. La
profondeur maximale est de huit niveaux.

Le backend utilisé est celui du build.py d’outils lancé, avec la politique locale
du projet sélectionné ; il ne lance pas un ancien wrapper arbitraire du tag.
Le manifeste enregistre le commit et l’empreinte des fichiers Python des outils.
Le core Arduino exigé et les dépendances doivent être déjà installés ; le
backend contrôle core, partitions, politique et exigences de bibliothèques.
Les bibliothèques effectivement signalées par le rapport de compilation sont
consignées si disponibles. L’OS, les chemins de build et les macros date/heure
peuvent influer sur les octets : un tag n’est pas une promesse de build identique.

## Contenu de l’archive

```text
v1.2.0/
├── release-manifest.json       # écrit en dernier après la chaîne de build
├── full/
│   ├── mon-projet.app.bin      # application exacte, jamais le merged.bin
│   ├── mon-projet-00010200.ota # si full_ota configuré
│   ├── ota-manifest.json
│   └── z2m-index.json          # si full_ota configuré
├── components/                # binaires USB et LittleFS produits
├── build/                     # logs privés, config, CSV, exigences
└── deltas/
    └── from-00010100/
        ├── base.app.bin       # copie exacte pour vérification autonome
        ├── *.delta.bin
        ├── *.delta.ota
        ├── delta-manifest.json
        └── z2m-index.json
```

Le manifeste contient identité, version, tag/commit/sous-modules, paramètres de
build, empreinte du tool, empreintes des entrées privées et inventaire des
sorties. Les logs peuvent contenir des chemins locaux ou des diagnostics privés.
Les binaires peuvent contenir des credentials compilés. Dossiers privés `0700`
et fichiers `0600` sont appliqués sur les systèmes qui respectent ces permissions.
Sur Windows, protéger également les ACL du dossier. Ne pas publier ces archives
sur GitHub, dans `/www` ou sur un hébergement public.

Le scratch reste dans `build/release-work/tag-…` du projet, ignoré par Git :
source exportée, inputs privés copiés et log y restent disponibles pour diagnostic.
Le tool ne les nettoie pas automatiquement. Une erreur laisse une destination
marquée `.incomplete`, sans manifeste complet ; la vérification la refuse.
Ne pas utiliser cette destination pour un appareil, même si quelques fichiers
y existent déjà.

Les composants sont associés au sketch et au CSV sélectionnés. LittleFS doit
avoir exactement la taille de sa partition ; son absence est refusée si `data/`
était présent. La table de partitions compilée doit correspondre au CSV, le
bootloader tenir dans sa zone, et le merged — s’il est fourni — avoir la taille
flash et contenir les mêmes bootloader/table/application aux bons offsets.
Ces contrôles structurels ne certifient pas le démarrage d’une carte physique.

Le vérificateur refuse fichiers manquants/ajoutés/modifiés, liens, chemins sortants,
conteneur full incohérent, mauvais modèle/version, profils incompatibles et
deltas ne reconstruisant pas exactement la cible. Limites : 4096 fichiers,
64 Mio par fichier et 4 Mio pour le manifeste principal. Les empreintes vérifient
l’intégrité/cohérence, pas une signature ni l’authenticité d’un auteur.

## Bases et versions

Le delta utilise le **binaire réellement archivé**, jamais une recompilation du
vieux tag. Il peut aller directement de 1.0 à 1.5 si le décodeur et son profil le
permettent ; aucune chaîne 1.1→1.2→… n’est calculée automatiquement. Chaque base
fournie doit avoir une version distincte, antérieure à la cible et au moins égale
au minimum du profil. L’index delta contraint minFileVersion=maxFileVersion à la
version source ; le décodeur vérifie aussi le hash exact de cette base.

Les nouvelles bases doivent avoir un profil de décodeur normalisé strictement
identique à celui de la cible. Les anciennes releases B4E contenant
`ota-manifest.json`, l’application, le full et son index sont acceptées après
vérification, sans réécriture, **avec une déclaration explicite** du contrat du
décodeur installé dans cette base :

```sh
python3 build.py release build --ref v1.0.5 \
  --base-release private-artifacts/releases/v1.0.4 \
  --legacy-base-profile tools/ota-profile.json \
  --output private-artifacts/validation/release-cli/v1.0.5
```

Ce fichier doit décrire le firmware **de base**, pas seulement la cible souhaitée.
Le tool vérifie qu’il correspond au profil cible et archive la déclaration.
L’ancien format ne permet pas de prouver rétroactivement le protocole du décodeur
à partir du numéro de version : cette déclaration repose sur le contrat connu
et conservé du projet. Un éventuel manifeste FS legacy est contrôlé pour modèle,
version, taille déclarée et hash ; le FS de la base n’entre pas dans le delta.
Les nouveaux FS sont toujours contrôlés contre leur CSV de partitions archivé. Les nouvelles
archives sont autoportantes pour leur vérification delta grâce aux bases copiées.
Conserver aussi les releases originales, qui décrivent ce qui a été installé.

Une nouvelle compilation d’un même tag/version peut produire d’autres octets.
Ne pas remplacer une ancienne archive par ce résultat et ne pas mélanger leurs
indices de déploiement. Pour publier un firmware modifié, incrémenter sa version,
commiter et créer un nouveau tag. L’outil n’incrémente ni ne réécrit les versions.

Le déploiement reste une étape distincte : préparer une copie des index avec les
URL accessibles à Z2M, garder un index full séparé comme repli et suivre
[le guide OTA](../ota/readme.md). Ni génération, ni verify, ni plan ne touchent HA.

## Validation

Les tests utilisent de vrais dépôts Git locaux (tags, espaces, sous-modules), des
images ESP32-C6 synthétiques valides et le vrai detools pour reconstruire les
cibles. Les tests de compilation contrôlent la frontière du processus backend ;
la validation B4E réelle vérifie séparément le compilateur Arduino installé.

```sh
python3 -m unittest discover -s tests -v
# Installer les dépendances delta pour exécuter aussi les tests d’archives :
python3 -m pip install -r requirements-delta.txt
```
