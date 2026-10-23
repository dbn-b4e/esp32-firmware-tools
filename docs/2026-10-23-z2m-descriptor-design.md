# Convertisseur Z2M générique depuis le firmware

Fonctions demandées pour l'exemple : entrée BOOT (GPIO9), sortie LED (GPIO2),
température simulée. Broches configurables. Le générateur ne dépend ni d'Arduino,
ni d'OZ, ni du C6 : son entrée est un descriptif JSON versionné.

Choix d'implémentation proposé : le firmware exporte `Z2M_DESCRIPTOR {json}` par
la commande console `describe`. Le même tableau constant détermine identité,
numéros d'endpoints, types et JSON dans le démonstrateur. Les noms/accès/unités
ne sont pas devinés depuis un binaire. L'interview Z2M peut fournir une base de
découverte, mais son import automatique n'est pas nécessaire au contrat initial.
La question de préférence utilisateur reste ouverte ; le noyau JSON sert dans
les deux cas et la capture USB est un adaptateur indépendant.

Modules : z2m/converter.py (validation/rendu/CLI), z2m/serial_capture.py (capture
pyserial optionnelle), exemples sous examples/c6-zigbee-demo/. Pas de copie du
générateur OZ PolyForm Noncommercial dans le dépôt MIT. Implémentation basée sur
les API publiques modernExtend et l'API Zigbee Arduino installée 3.3.4.

Schéma 1 : device{model,manufacturer,description,firmware_version}, endpoints
avec id/name, clusters input/output et features typées ; ota booléen explicite.
Types initiaux : on_off, binary_input, temperature, humidity. Inconnus refusés,
identifiants uniques, valeurs et cohérence des clusters vérifiés. Pas de code
JavaScript libre dans le JSON. Sortie déterministe .mjs, fingerprint exact
manufacturer+model, chaînes encodées JSON, aucun secret ou identifiant réseau.

CLI : generate --input --output [--force], validate --input ; capture --port
--output [--baud --timeout] via pyserial. Création exclusive par défaut, sortie
égale à l'entrée et symlinks de sortie refusés. Capture limitée en taille/temps,
seul le JSON du protocole est conservé, pas les autres logs série.

Exemple : trois EP séparés, aucun WiFi/MQTT/secret, aucune commande de relais.
Loop réservée à la console ; tâche applicative pour BOOT/température/LED.
Callback Zigbee écrit seulement une consigne atomique ; une seule tâche écrit
la LED. Débounce de BOOT et périodicité de reporting explicites. Pas de reset
Zigbee implicite sur appui long. Exemple sans client OTA, pour rester minimal.

Vérification : tests entrées invalides/injection/symlinks/non-écrasement,
JSON exporté par le vrai header C++ exécuté en natif, compilation C6 réelle,
chargement du .mjs avec zigbee-herdsman-converters 26.115.1 et contrôle des
exposes/conversions. B4E reste en firmware 1.0.5 ; exemple non flashé sans accord
sur le changement de firmware et l'interview de ce device.
