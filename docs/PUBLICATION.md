# Contrôle de publication — 23 octobre 2026

## Périmètre et méthode

Contrôle des fichiers de l’index Git et de tous les blobs de l’historique
accessible avant publication du générateur de convertisseurs et de l’exemple.
Le point de contrôle initial était `d55039e9c849c0acfde143919bf769edc828d502` :
32 commits, 118 blobs uniques, 1 091 956 octets. L’index après correctifs et guides
contenait 68 fichiers, 335 742 octets, avant ajout de ce rapport.

Recherche de formats de tokens GitHub, clés privées, clés AWS, JWT et affectations
littérales de secrets ; contrôle des chemins de configuration privée et des
binaires firmware. Contrôle complémentaire de l’index pour chemins personnels,
adresses d’infrastructure privée et blobs binaires. Les valeurs correspondantes
ne sont pas imprimées dans les rapports. Inspection des fichiers, dépendances,
licences et revue indépendante du code ajouté complètent les expressions
régulières. Les preuves détaillées et binaires de validation restent hors Git.

Résultat : aucun secret identifié, aucune configuration réseau privée ni
application firmware compilée suivie dans le périmètre inspecté. Les exemples
emploient une identité fictive et aucun WiFi/MQTT. Les chaînes de test contenant
« password » sont des données factices servant à vérifier que les logs ne sont
pas exportés. Les scripts de génération ne récupèrent pas de credentials.

## Métadonnées publiques et licences

Le nom d’auteur et son adresse professionnelle restent visibles dans
l’historique Git. Il ne s’agit donc pas d’un dépôt sans aucune donnée personnelle.
Aucune réécriture de l’historique n’a été réalisée.

Le code commun et les nouveaux modules sont MIT. L’historique de l’ancien
OTA-Builder et ses notices ont été conservés. La référence Espressif optionnelle
reste Apache-2.0 avec ses en-têtes et sa licence. Aucun code OZ sous PolyForm
Noncommercial n’a été copié. Les dépendances Arduino, Python et npm restent des
composants externes soumis à leurs licences ; voir NOTICE.md.
Les anciens libellés SxS visibles dans l’historique des outils ne contiennent pas
le firmware ou la configuration du projet SxS, qui n’a pas été modifié.

L’audit npm des dépendances verrouillées des tests Z2M, effectué le 23 octobre
2026 contre le registre public, retourne zéro vulnérabilité connue. Ce résultat
est daté, limité à cet écosystème et ne vaut pas certification de sécurité du
firmware ou de toutes les dépendances de la chaîne.

## Correctifs issus de la revue

- Validation globale des noms de propriétés finaux : refus des collisions entre
  types et entre endpoints, y compris les alias dus aux underscores.
- Exclusion exacte des headers standard C++ dans le diagnostic des bibliothèques,
  sans masquer les headers tiers.
- Timeout d’écriture pyserial en plus du timeout de lecture ; fermeture garantie
  de la connexion en cas d’échec.
- Documentation de la limite des drapeaux de connexion Arduino et de la portée
  réelle des tests physiques.

Chaque correctif dispose d’une régression observée en échec avant correction,
puis en succès. Les tests runtime utilisent la vraie bibliothèque
zigbee-herdsman-converters, pas un substitut de son API.

## Validation et limites

34 tests Python communs, 19 OTA et 4 tests runtime JavaScript passent sur Mac.
L’exemple compile réellement avec le core Arduino 3.3.4. Le header C++ du FW est
exécuté sur hôte pour vérifier l’export et le convertisseur archivés. B4E est
recompilé et testé séparément avec son sous-module et sa politique locale.
La CI exécute les suites Python sur Linux/macOS/Windows et Python 3.10/3.13,
ainsi que le runtime JavaScript sur Node 22/24.

Un flash USB physique et une capture `describe` ont ensuite été vérifiés sur C6 :
le JSON réel et son convertisseur sont identiques aux snapshots testés. Le
changement de modèle depuis B4E a révélé un crash lié aux anciens enregistrements
Zigbee, supprimé après effacement explicite du seul stockage Zigbee sauvegardé.
L’appairage et les remontées ont ensuite été validés, comme détaillé plus bas ;
les essais prolongés de reconnexion et après coupure restent à réaliser. Le SDK
Arduino utilise des drapeaux de connexion ordinaires qui ne constituent pas une
preuve de liaison en direct. L’exemple ne doit pas servir de watchdog de
sécurité ou de système de commande de chaudière sans conception complémentaire.

Les expressions régulières ne prouvent pas l’absence absolue de secrets.
Un descriptif futur peut contenir un libellé privé choisi par son auteur ; il
faut inspecter le JSON avant de le publier. Les hashes OTA vérifient l’intégrité,
pas une signature cryptographique. La génération de fichiers n’autorise pas un
déploiement automatique sur HA, Z2M ou une carte en production.


## Validation du générateur sur le réseau Zigbee

Après rétablissement de l’alimentation du coordinateur et autorisation
utilisateur, le convertisseur `c6-tools-demo.mjs` a été chargé à chaud et une
nouvelle interview a été exécutée sur le seul C6 de test. Z2M a confirmé le
modèle `C6-TOOLS-DEMO`, le fabricant `Example` et les endpoints 10/20/30.
La température simulée a évolué, BOOT a été observé dans ses deux états et la
sortie LED à ON. L’ancienne fiche avait conservé les endpoints B4E car l’adresse
IEEE matérielle restait identique ; une nouvelle interview était indispensable.

Le test réseau a aussi révélé des rapports manuels malformés issus des requêtes
partiellement initialisées du core Arduino 3.3.4. Le correctif 1.0.1 est local à
l’exemple et ne modifie aucune bibliothèque Arduino installée globalement.


Après flash de la correction 1.0.1, `describe` a confirmé la version réelle et
l’identité inchangée. Le contrôle réseau a observé 21 rapports standards valides,
zéro rapport malformé `raw` et zéro erreur de configuration sur la fenêtre de
vérification. La température a continué à évoluer après redémarrage ; aucune
nouvelle interview n’a été nécessaire pour ce correctif compatible.


## Orchestrateur de releases depuis tags

La commande `build.py release plan|build|verify` a été testée avec de vrais Git
locaux, un projet en sous-dossier, des sous-modules épinglés et des archives ESP
valides. 60 tests Python communs, 19 tests OTA et 4 tests runtime Z2M passent sur
Mac. Une revue indépendante a comparé fonction par fonction les anciens scripts
B4E et la nouvelle orchestration ; les écarts importants de profil de base et
de validation filesystem ont été reproduits puis corrigés avec des régressions.

La validation réelle finale utilise le code d’outils `9f136d3` et le tag local
B4E v1.0.5 : compilation en copie isolée, full de 1 560 466 octets, delta depuis
l’archive exacte v1.0.4 de 38 844 octets, LittleFS de 372 736 octets. Le delta est
reconstruit exactement et `release verify` contrôle aussi les composants USB,
le CSV/table de partitions et le filesystem. Aucun déploiement sur carte ou HA
n’a été réalisé pour ce chantier. Les binaires et logs restent privés.

Le scan d’historique jusqu’au code `9f136d3` couvre 169 blobs (1 619 853 octets),
sans motif de secret ou artefact privé identifié. Les nouveaux fichiers publics
contiennent configuration de packaging et tests synthétiques ; les secrets
restent dans des entrées locales ignorées explicitement déclarées. Le profil
legacy est une déclaration du contrat connu de l’ancien FW, pas une preuve
cryptographique déduite rétroactivement de son numéro de version.
