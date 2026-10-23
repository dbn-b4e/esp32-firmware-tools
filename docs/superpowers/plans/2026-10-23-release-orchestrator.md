# Release depuis un tag — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans, inline. Steps use checkbox syntax.

**Goal:** Un seul build.py sélectionne un tag, compile sa source isolée et archive application/full/deltas vérifiés.
**Architecture:** Nouveau package release_tools, piloté par build.py avant le backend Arduino. Export Git des objets du tag, sous-modules récursifs depuis leurs objets locaux ; aucun checkout du projet courant. Packaging sur les modules OTA existants. Pas de firmware, flash ou infra dans ce chantier.
**Tech Stack:** Python >=3.10, Git, Arduino CLI ; detools/esptool uniquement pour validation C6/deltas.
**Spec:** Le présent contrat et l’accord utilisateur « ok do it » après proposition du CLI tag→build→full/diff.

## Contrat et choix

- Garder build.py unique : `--project PROJECT release plan|build --ref TAG [--base-release ARCHIVE ...] [--output RELATIVE]` ; `release verify --archive RELATIVE`.
- Comparaison : recompiler chaque base est impropre aux deltas exacts ; modifier le checkout courant met le travail local en danger. Choix d’implémentation : exporter les objets Git, réutiliser les archives exactes pour les bases.
- Sélection locale de refs/tags seulement, SHA de commit figé avant tout travail ; version issue du header sélectionné, tag semver cohérent si son nom est semver.
- Projet éventuellement sous-dossier d’un Git (exemple C6), snapshot Git complet et préfixe projet conservé. Symlinks et liens tar refusés. Sous-modules au gitlink exact, sans réseau implicite ; objets manquants = erreur explicite.
- release-config.json dans la source sélectionnée : schema_version=1, name, local_inputs (fichiers relatifs explicitement autorisés et ignorés par Git), full_ota optionnel (paramètres build_ota sans file_version), delta_profile optionnel (chemin JSON relatif). Projet sans client OTA : full_ota absent, archive de build uniquement.
- Paramètres du tag autoritaires ; les valeurs privées restent uniquement dans les fichiers ignorés déclarés. Empreinte et chemin logique archivés, jamais leur contenu dans le manifeste ; logs/artefacts sont privés.
- Le backend courant des outils compile la source du tag avec sa politique locale. Son identité Git/empreinte de code est enregistrée ; pas d’exécution d’un ancien wrapper arbitraire.
- Scratch dans build/release-work du projet, ignoré par Git, permissions privées. Destinations obligatoirement confinées au projet et ignorées ; nouvelle destination exclusive, aucune option force. Manifeste complet écrit en dernier. Échec conserve diagnostics, jamais une archive validée.
- Application, composants USB et LittleFS exacts archivés ; source commit/tag/sous-modules, core/options, versions des bibliothèques compilées si disponibles, paramètres et empreintes d’entrées et de sorties enregistrés.
- Full : application seulement, conteneur/empreintes/index vérifiés. Delta : profil identique au full, marqueur modèle/version et image ESP valides, version base autorisée, reconstruction exacte, index de base exacte. Plusieurs bases possibles, version base dupliquée refusée.
- Lire aussi les anciennes archives ota-manifest.json B4E, vérifier image/hash/full avant utilisation ; ne pas modifier ces bases.
- Archive autoportante : copie privée des bases nécessaires dans chaque dossier delta, manifeste et index natifs conservés. verify rejette corruption, chemins sortants, symlinks et fichiers inattendus ; hashes ≠ signature.
- build.py historique inchangé en dehors du dispatch release ; pas de Qt, installation globale, fetch, flash ou action HA/Z2M.

## Global Constraints

Python >=3.10 ; un changement vérifié à la fois ; aucun repo/scratch dans /tmp système ; SxS figé ; aucune fuite de secrets ; dépendances OTA déjà épinglées.

## Review Focus

1. Tag modifié ou entrées locales modifiées entre plan et build : SHA/version/empreintes doivent correspondre à ce qui est effectivement compilé.
2. Archives hostiles : traversée, symlinks, incohérence profil/version/hash, base corrompue ; refus avant publication.
3. Sous-modules : objets du gitlink exact requis, pas la source sale du checkout courant.
4. Build défaillant ou sorties partielles : aucune archive acceptée, destination existante jamais écrasée, logs privés.
5. Mac/Linux/Windows, chemins avec espaces, tagged project in monorepo ; aucune concaténation shell.

## Tasks

### Task 1 — Sources et plan

Files: release_tools/source.py, config.py ; tests/test_release_source.py.
- [x] Écrire tests Git réel : tag annoté/léger, dirty checkout ignoré, sous-dossier, sous-module exact, lien/traversée refusés, local_inputs strictement ignorés, version tag/header, sortie confinée/ignorée/existante.
- [x] Observer RED, implémenter sélection/export/plan, vérifier GREEN et suite, commit.

### Task 2 — Archives full et delta

Files: release_tools/archive.py ; tests/test_release_archive.py.
- [x] Tests avec vraies images ESP synthétiques et detools : full, corruption, mauvais modèle/version, anciennes bases B4E, bases multiples, delta direct 1→5, archive autoportante et refus des fichiers non déclarés/liens.
- [x] Observer RED, réutiliser les primitives OTA existantes, GREEN et suite, commit.

### Task 3 — Orchestration CLI

Files: release_tools/cli.py, runner.py, build.py ; tests/test_release_cli.py ; exemple release-config.json.
- [ ] Tests CLI dans Git synthétique : plan sans outil Arduino, dispatch, échec sans archive complète, chemin avec espaces, réussite avec processus backend contrôlé puis vrais packages, verify.
- [ ] Observer RED, implémenter build isolé et publication exclusive, GREEN et suite, commit.

### Task 4 — B4E et validation réelle

Files: B4E release-config.json, tools/ota-profile.json ; docs et README outils ; B4E docs/BUILD.md.
- [ ] Configurer le profil sans changer le firmware ni le core, checkpoint et tag de validation local explicite.
- [ ] Compiler réellement ce tag B4E depuis la copie isolée, full + delta depuis archive exacte v1.0.4, verify hors ligne ; aucune action sur carte/HA.
- [ ] Vérifier docs contre commandes réelles, audit secrets historique + nouveaux fichiers, reviewer indépendant sur l’ensemble et fidélité des gardes OTA ancien/nouveau.
- [ ] Fixes importants RED→GREEN, suites complètes, publication outils, sous-module B4E épinglé, commits propres.

## Ledger

- Base outils : 6e16099 ; B4E 4e1ab5e. Choix du snapshot/export et du CLI inline par l’implémentation, pas présentés comme choix utilisateur explicites.

- Task 1: complete — six régressions RED→GREEN ; suite commune 40 tests OK. Git réel, tags annotés, sous-modules épinglés et entrée locale changée couverts.
- Workspace : worktree persistante dans tmp/release-orchestrator, ignorée ; les outils natifs sont liés au checkout de la tâche WIMEREUX et ne permettent pas de choisir ce dépôt d’outils. Aucun accès infra dans ce chantier.

- Task 2: complete — quatre tests d’archives RED→GREEN, 44 tests communs OK avec dépendances delta. Full + deltas 3→5/4→5 reconstruits, bases legacy et autoportance contrôlées.
