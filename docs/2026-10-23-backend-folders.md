# Sous-dossiers des outils — décision approuvée

Un seul dépôt Git pour arduino/, ota/, common/, tests/ et docs/. B4E conserve
son unique sous-module. SxS n'est ni lu ni modifié par cette migration.

Plan : checkpoint, tests des imports attendus (échec), déplacement Git du
backend esp32_tools vers arduino, déplacement de la console portable vers
common, adaptation des imports et documentation. Aucun algorithme ou format
OTA ne change ; le lanceur racine continue d'appeler le backend Arduino.
Les dossiers ESP-IDF/PlatformIO seront créés lorsqu'ils seront implémentés.

Validation : suites outils et OTA, revue indépendante des mécanismes avant/après,
B4E Python/Node, contrôles environnement et compilation réelle B4E sans flash.
Puis commits, push outils et mise à jour du pointeur du sous-module B4E.

Résultats : 19 tests moteur/imports et 19 tests OTA passent. Les 28 tests B4E
(dont décodeur natif ASan/UBSan) et 2 tests web passent ; compilation réelle
B4E + LittleFS et génération/vérification OTA réussies sans écriture device.
Revue indépendante : 74 fonctions/classes inchangées hors imports, aucun
contrôle perdu. Le shim de rapports B4E importe maintenant arduino.engine.
Les trois sous-dossiers résolvent le même toplevel Git ; aucun sous-module
interne au dépôt d'outils. Les contraintes processus/cache/concurrence restent
celles documentées dans README : un processus neuf et un build par projet.
