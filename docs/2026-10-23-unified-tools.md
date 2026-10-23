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
- [ ] Baseline des deux suites et checkpoint Git.
- [ ] Import par git subtree, sans squash, de l'historique OTA sous ota/.
- [ ] Test de l'import comme module, adaptation des imports uniquement.
- [ ] CI couvrant les deux suites et dépendances delta explicites.
- [ ] Raccord B4E, tests de non-régression et reproduction exacte des archives.
- [ ] Revue indépendante ancien/nouveau des contrôles critiques.
- [ ] Audit des fichiers ET de tous les blobs historiques avant publication.
- [ ] Documentation, commits, pointeur B4E, lien de migration dans ancien dépôt.

Pas de nouveau format différentiel, de changement du décodeur embarqué, de
compilation par tags, de Qt ou de déploiement HA/USB dans ce lot.

Validation : suites compilation et OTA conservées, B4E Python/Node, comparaison
byte-à-byte des conteneurs complets et delta sur archives privées existantes.
Les tests natifs du décodeur B4E restent dans B4E. Les tests hôtes OTA en CI ne
valident pas un transfert physique ou un nouveau protocole embarqué.
