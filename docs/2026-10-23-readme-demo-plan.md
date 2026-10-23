# Documentation publique, audit et démonstrateur C6

Demande : vérifier le sous-module B4E, compiler/tester, compléter README.md et
audit public du dépôt, fournir un exemple BOOT entrée + LED sortie + température
simulée, avec convertisseur .mjs et procédure Z2M/HA. SxS reste figé.

B4E utilise déjà 5608178 du dépôt commun. La recompilation et les suites B4E
sont relancées avant modification des outils. Le C6 reste en 1.0.5 pendant la
préparation locale de l'exemple ; aucune action HA/flash supplémentaire implicite.

OZ contient tools/oz/z2m_generator.py, ESM/modernExtend, couplé au schéma et au
plan d'endpoints OZ. Son dépôt est PolyForm Noncommercial, les outils sont MIT :
pas de copie de ce code dans les modules MIT. Un générateur réduit peut être
écrit sur l'API publique Z2M avec un contrat d'entrée indépendant du compilateur.

Étapes :
1. Corriger l'aide générique qui décrit actuellement une option --ota propre
   au wrapper B4E, sans modifier compilation/flash/OTA.
2. Définir la source du descriptif générique (export firmware recommandé ;
   interview Z2M possible pour la découverte). Discussion utilisateur en cours.
3. Implémenter le générateur et un exemple C6 avec mêmes endpoints et métadonnées,
   puis compiler réellement. BOOT GPIO9 / LED GPIO2 configurables ; pas de relais.
4. README complet confronté au code : installation, configuration, commandes,
   fichiers produits, full/diff, versions/bases exactes, exemple et manipulation,
   limites connues, tests et règles de publication.
5. Audit fichiers suivis + historique, dépendances/licences, aucun secret ou
   binaire/config privé ; revue indépendante avant publication et mise à jour
   du sous-module B4E.
