# Réunir compilation et OTA dans un seul dépôt

Décision approuvée : esp32-firmware-tools devient le dépôt commun ; le code OTA
vient de esp32C6-OTA-Builder avec historique, licences, documentation et tests.
B4E garde un seul sous-module fixé. SxS reste entièrement figé.

Organisation : moteur esp32_tools/ et build.py inchangés ; outils autonomes sous
ota/ avec leurs CLI existants. L'import Python ota.delta_ota doit fonctionner
comme le lancement direct. Les profils, garde-fous et formats binaires OTA
restent inchangés. Le packaging B4E reste une politique de projet ; il réutilise
le générateur commun plutôt qu'une copie locale.

Exécution :
- [x] Baseline des deux suites et checkpoint Git.
- [x] Import par git subtree, sans squash, de l'historique OTA sous ota/.
- [x] Test de l'import comme module, adaptation des imports uniquement.
- [x] CI couvrant les deux suites et dépendances delta explicites.
- [x] Raccord B4E, tests de non-régression et reproduction exacte des archives.
- [x] Revue indépendante ancien/nouveau des contrôles critiques.
- [x] Audit des fichiers ET de tous les blobs historiques avant publication.
- [x] Documentation, commits, pointeur B4E, lien de migration dans ancien dépôt.

Pas de nouveau format différentiel, de changement du décodeur embarqué, de
compilation par tags, de Qt ou de déploiement HA/USB dans ce lot.

Validation : suites compilation et OTA conservées, B4E Python/Node, comparaison
byte-à-byte des conteneurs complets et delta sur archives privées existantes.
Les tests natifs du décodeur B4E restent dans B4E. Les tests hôtes OTA en CI ne
valident pas un transfert physique ou un nouveau protocole embarqué.

Résultats : suites moteur 18/18 et OTA 19/19, suite B4E 28/28 et web 2/2.
Reproduction des deux OTA complètes archivées 1.0.3/1.0.4 et du delta 1.0.3→1.0.4 :
binaires, conteneurs, manifeste et index identiques octet à octet.
Revue indépendante : 14 fonctions/classes delta et 6 full identiques (AST),
aucune garde critique perdue. La politique B4E conserve son format historique ;
la reconstruction hôte est désormais bornée et la validation ESP delta renforcée.

Audit avant publication : 22 commits et 73 blobs du code intégré 962dd7f,
761 237 octets parcourus ; aucun motif de token/clé privée/secret littéral,
fichier binaire/config device, ni référence d'infrastructure privée détecté.
Les archives de validation restent dans le projet B4E privé, hors Git.
L'audit par motifs n'est pas une preuve mathématique d'absence de secret ;
les nouveaux fichiers concernent uniquement les outils et leur documentation.

Limites héritées conservées : B4E full/FS utilise build/ota comme staging mutable
(ne pas passer un dossier d'archives à l'API), et garde sa validation full
historique d'en-tête/identité/hashes. Le chemin delta contrôle aussi l'image ESP.
Une génération à la fois par dossier et un processus neuf par invocation ;
PROFILE est figé, mais sys.path/sys.modules et umask sont propres au processus.

Aucun changement firmware SxS/B4E et aucun déploiement USB/HA dans ce lot.
L'ancien dépôt est conservé en historique avec un lien vers ce dépôt unique.
