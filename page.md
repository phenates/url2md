Ce que vous allez apprendre
Section intitulée « Ce que vous allez apprendre »- Image vs Conteneur : la différence fondamentale que tout débutant doit maîtriser
- Cycle de vie : les états created, running, paused, stopped, dead
- Layers : pourquoi Docker est si efficace (cache, partage, téléchargement)
- Isolation : namespaces et cgroups sous le capot
- Architecture : client, daemon, registry — comment tout s’articule
En 30 secondes
Section intitulée « En 30 secondes »| Concept | Définition express |
|---|---|
| Image | Modèle immuable (read-only) composé de layers |
| Conteneur | Processus isolé + layer R/W (éphémère par défaut) |
docker run | Crée puis démarre un conteneur (create → start) |
| États | created → running ↔ paused → exited → removed |
| Daemon | dockerd orchestre via API ; le client docker envoie des requêtes |
| Layers | Chaque instruction Dockerfile = une couche partagée et cachée |
Prérequis
Section intitulée « Prérequis »Quelle est la différence entre image et conteneur ?
Section intitulée « Quelle est la différence entre image et conteneur ? »La distinction entre image et conteneur est la notion la plus importante à maîtriser. C’est la question que se posent tous les débutants — et la source de nombreuses confusions.
La réponse courte
Section intitulée « La réponse courte »| Image | Conteneur | |
|---|---|---|
| Nature | Modèle immuable | Instance (processus) |
| Écriture | Read-only | Layer R/W |
| Persistance | Stockée sur disque | Éphémère sans volume |
| Multiplicité | 1 image → N conteneurs | 1 conteneur = 1 exécution |
| Analogie | Classe (POO) / Moule | Objet / Gâteau fabriqué |
L’image : le modèle immuable
Section intitulée « L’image : le modèle immuable »Une image Docker est un package en lecture seule contenant tout le nécessaire pour exécuter une application :
- Système de fichiers de base (OS minimal)
- Dépendances et bibliothèques
- Code de l’application
- Variables d’environnement
- Commande de démarrage
Caractéristiques clés :
| Propriété | Description |
|---|---|
| Immuable | Une fois créée, une image ne change jamais |
| Versionnée | Identifiée par un tag (ex: nginx:1.25 ) |
| Portable | Fonctionne identiquement partout |
| Composée de layers | Chaque instruction Dockerfile = une couche |
Analogie : Une image est comme une classe en programmation orientée objet, ou un moule pour faire des gâteaux. Elle définit la structure mais ne s’exécute pas elle-même.
Le conteneur : l’instance en exécution
Section intitulée « Le conteneur : l’instance en exécution »Un conteneur est une instance d’une image en cours d’exécution. C’est un processus isolé avec son propre :
- Système de fichiers (copie de l’image + layer d’écriture)
- Espace réseau
- Arborescence de processus (PID)
- Hostname
Caractéristiques clés :
| Propriété | Description |
|---|---|
| Éphémère | Par défaut, les données disparaissent à la suppression |
| Isolé | Séparé des autres conteneurs et de l’hôte |
| Layer R/W | Peut écrire dans sa couche propre (non persistante) |
| Léger | Partage le kernel avec l’hôte |
Analogie : Un conteneur est comme un objet instancié depuis une classe, ou un gâteau fabriqué avec le moule.
→ Pour manipuler images et conteneurs : Guide CLI Docker
Image → Conteneur : le flux
Section intitulée « Image → Conteneur : le flux »Que fait exactement docker run
?
Section intitulée « Que fait exactement docker run ? »Quand vous exécutez docker run nginx:alpine
, Docker effectue plusieurs opérations en séquence :
-
Recherche l’image localement, sinon la télécharge (
docker pull
) -
Crée un conteneur avec un layer R/W (
docker create
) -
Configure l’isolation : namespaces, cgroups, réseau
-
Démarre le processus principal (
docker start
)
C’est pourquoi docker run
= docker create
+ docker start
.
Cycle de vie d’un conteneur
Section intitulée « Cycle de vie d’un conteneur »Un conteneur passe par plusieurs états au cours de sa vie. Comprendre ces états vous permet de diagnostiquer rapidement pourquoi un conteneur ne fonctionne pas comme prévu.
Diagramme des états
Section intitulée « Diagramme des états »Les états détaillés
Section intitulée « Les états détaillés »Le conteneur est créé mais pas démarré. Le layer R/W existe, les ressources sont allouées, mais aucun processus ne tourne.
Cas d’usage : préparer un conteneur avec des configurations avant démarrage.
Le conteneur est actif, son processus principal (PID 1) s’exécute.
Le processus est suspendu (signal SIGSTOP). Le conteneur reste en mémoire mais ne consomme plus de CPU.
Cas d’usage : debugging, snapshot mémoire, migration live.
stopped / exited
Section intitulée « stopped / exited »Le processus principal s’est terminé (normalement ou avec erreur). Le conteneur et son layer R/W existent toujours.
Différence entre docker stop
et docker kill
?
Section intitulée « Différence entre docker stop et docker kill ? »| Commande | Signal | Délai | Usage |
|---|---|---|---|
docker stop | SIGTERM → SIGKILL | 10s par défaut | Arrêt propre (graceful) |
docker kill | SIGKILL | Immédiat | Forcer l’arrêt |
Règle : utilisez toujours docker stop
sauf si le conteneur ne répond plus.
Comment savoir pourquoi un conteneur est en Exited (137) ?
Section intitulée « Comment savoir pourquoi un conteneur est en Exited (137) ? »| Code de sortie | Signification |
|---|---|
0 | Succès — le processus s’est terminé normalement |
1-125 | Erreur application |
126 | Commande non exécutable |
127 | Commande non trouvée |
137 | SIGKILL (OOM killer ou docker kill ) |
143 | SIGTERM (docker stop ) |
→ Pour approfondir le troubleshooting : Commandes Docker CLI
État d’erreur où le conteneur ne peut pas être redémarré ni supprimé normalement. Généralement causé par un problème de ressources ou de driver de stockage.
Commandes et transitions
Section intitulée « Commandes et transitions »| Commande | Transition |
|---|---|
docker create | → created |
docker start | created/exited → running |
docker run | → created → running |
docker pause | running → paused |
docker unpause | paused → running |
docker stop | running → exited |
docker kill | running → exited |
docker restart | running → exited → running |
docker rm | exited → removed |
Pourquoi Docker utilise des layers ?
Section intitulée « Pourquoi Docker utilise des layers ? »Docker utilise un système de couches (layers) pour les images, optimisant le stockage et les téléchargements. C’est ce qui rend Docker si efficace.
Principe des layers
Section intitulée « Principe des layers »Chaque instruction d’un Dockerfile crée une couche :
Les 4 avantages du système de layers
Section intitulée « Les 4 avantages du système de layers »| Avantage | Description | Impact |
|---|---|---|
| Partage | Les layers communs sont partagés entre images | Économie disque |
| Cache | Les layers inchangés sont réutilisés lors du build | Builds rapides |
| Téléchargement | Seuls les layers manquants sont téléchargés | Réseau optimisé |
| Immutabilité | Chaque layer a un hash unique | Reproductibilité |
Exemple de partage :
→ Pour optimiser vos builds : Écrire un Dockerfile
Copy-on-Write (CoW)
Section intitulée « Copy-on-Write (CoW) »Quand un conteneur modifie un fichier d’un layer en lecture seule :
- Docker copie le fichier dans le layer R/W du conteneur
- Les modifications s’appliquent à la copie
- Le layer original reste intact
→ Pour la persistance des données : Volumes Docker
Pourquoi les données disparaissent quand je supprime un conteneur ?
Section intitulée « Pourquoi les données disparaissent quand je supprime un conteneur ? »Le layer R/W (lecture/écriture) du conteneur est éphémère. Quand vous supprimez le conteneur (docker rm
), ce layer disparaît avec toutes les données écrites.
Solutions pour persister les données :
| Méthode | Usage | Commande |
|---|---|---|
| Volume nommé | Bases de données, fichiers importants | -v mydata:/var/lib/data |
| Bind mount | Développement (code source) | -v ./src:/app |
| docker commit | Sauvegarder l’état (rarement recommandé) | docker commit container image |
Inspecter les layers
Section intitulée « Inspecter les layers »Isolation : namespaces et cgroups
Section intitulée « Isolation : namespaces et cgroups »Docker utilise deux mécanismes du kernel Linux pour isoler les conteneurs. Comprendre ces mécanismes vous aide à diagnostiquer les problèmes et à renforcer la sécurité.
À quoi servent namespaces et cgroups ?
Section intitulée « À quoi servent namespaces et cgroups ? »| Mécanisme | Rôle | Analogie |
|---|---|---|
| Namespaces | Isolent ce que le conteneur voit | Murs entre appartements |
| Cgroups | Limitent ce que le conteneur consomme | Compteurs d’eau/électricité |
Namespaces
Section intitulée « Namespaces »Les namespaces créent des vues isolées des ressources système :
| Namespace | Isole | Effet |
|---|---|---|
| PID | Processus | Le conteneur voit ses propres PIDs (1, 2, 3…) |
| Network | Réseau | Interface réseau, IP, ports propres |
| Mount | Filesystem | Points de montage indépendants |
| UTS | Hostname | Hostname et domainname propres |
| IPC | IPC | Mémoire partagée, sémaphores isolés |
| User | Utilisateurs | Mapping UID/GID (rootless mode) |
Visualisation :
Pourquoi un conteneur a un PID 1 ?
Section intitulée « Pourquoi un conteneur a un PID 1 ? »Dans un conteneur, le processus principal devient PID 1 grâce au namespace PID. Ce processus :
- Reçoit les signaux (SIGTERM, SIGKILL)
- Doit gérer les processus orphelins (reaping)
- Sa mort = arrêt du conteneur
Les cgroups (control groups) limitent et comptabilisent les ressources :
| Ressource | Option docker run | Exemple |
|---|---|---|
| CPU | --cpus | --cpus 0.5 (50% d’un CPU) |
| Mémoire | --memory | --memory 256m |
| I/O | --device-read-bps | Limiter lecture disque |
| PIDs | --pids-limit | Nombre max de processus |
Docker : conteneur vs VM, quelle différence ?
Section intitulée « Docker : conteneur vs VM, quelle différence ? »| Critère | Conteneur | VM |
|---|---|---|
| Isolation | Kernel partagé (namespaces/cgroups) | Hyperviseur (isolation matérielle) |
| Démarrage | Secondes | Minutes |
| Taille | Mo | Go |
| Overhead | Minimal | Significatif (OS complet) |
| Sécurité | Surface d’attaque plus large | Isolation plus forte |
→ Pour renforcer l’isolation : Sécuriser Docker
Architecture Docker
Section intitulée « Architecture Docker »Docker utilise une architecture client-serveur où le client communique avec le daemon via une API REST.
Vue d’ensemble
Section intitulée « Vue d’ensemble »Le daemon dockerd
Section intitulée « Le daemon dockerd »Le daemon Docker (dockerd
) est le cœur du système :
- Écoute sur le socket Unix
/var/run/docker.sock
- Gère les images, conteneurs, réseaux et volumes
- S’exécute en root par défaut (attention sécurité)
- Communique avec
containerd
pour l’exécution
Pourquoi le groupe docker équivaut à root ?
Section intitulée « Pourquoi le groupe docker équivaut à root ? »Le client docker
Section intitulée « Le client docker »Le client est l’outil en ligne de commande que vous utilisez :
- Envoie des requêtes au daemon via l’API REST
- Peut se connecter à un daemon distant
- Configuration dans
~/.docker/config.json
Les registries
Section intitulée « Les registries »Un registry stocke et distribue les images Docker :
| Registry | Type | Usage |
|---|---|---|
| Docker Hub | Public | Registry par défaut, images officielles |
| GitHub Container Registry | Public/Privé | Intégré à GitHub |
| Harbor | Privé | Enterprise, on-premise |
| AWS ECR | Privé | AWS natif |
| Google Artifact Registry | Privé | GCP natif |
Résumé visuel
Section intitulée « Résumé visuel »Ce diagramme synthétise l’écosystème Docker : les images (templates), les conteneurs (instances), les volumes (persistance), le daemon qui orchestre le tout, et le kernel Linux partagé qui rend cette légèreté possible.
À retenir
Section intitulée « À retenir »- Image = modèle immuable : template read-only composé de layers
- Conteneur = instance éphémère : processus isolé avec son propre layer R/W
docker run
= create + start : recherche l’image, crée le conteneur, démarre- Cycle de vie : created → running ↔ paused → exited → removed
- Layers : chaque instruction Dockerfile = une couche partagée et cachée
- Namespaces : isolation des vues système (PID, network, mount…)
- Cgroups : limitation des ressources (CPU, mémoire, I/O)
- Socket Docker = root : protégez
/var/run/docker.sock
Contrôle des connaissances
Section intitulée « Contrôle des connaissances »Contrôle de connaissances
Validez vos connaissances avec ce quiz interactif
Informations
- Le chronomètre démarre au clic sur Démarrer
- Questions à choix multiples, vrai/faux et réponses courtes
- Vous pouvez naviguer entre les questions
- Les résultats détaillés sont affichés à la fin
Lance le quiz et démarre le chronomètre
Vérification
(0/0)Profil de compétences
Quoi faire maintenant
Ressources pour progresser
Des indices pour retenter votre chance ?
Nouveau quiz complet avec des questions aléatoires
Retravailler uniquement les questions ratées
Retour à la liste des certifications
Prochaines étapes
Section intitulée « Prochaines étapes »FAQ — Questions fréquentes
Section intitulée « FAQ — Questions fréquentes »Définition
Une image Docker est un modèle immuable (read-only) composé de layers, contenant le code, les dépendances et la configuration. Un conteneur est une instance en cours d'exécution de cette image, avec son propre layer R/W éphémère.
Comparaison
| Aspect | Image | Conteneur |
|---|---|---|
| Nature | Modèle immuable | Instance (processus) |
| Écriture | Read-only | Layer R/W |
| Persistance | Stockée sur disque | Éphémère sans volume |
| Multiplicité | 1 image → N conteneurs | 1 conteneur = 1 exécution |
Analogie
- Image = Classe (POO) ou moule à gâteaux
- Conteneur = Objet instancié ou gâteau fabriqué
Différences fondamentales
| Critère | Conteneur | VM |
|---|---|---|
| Isolation | Kernel partagé (namespaces/cgroups) | Hyperviseur (isolation matérielle) |
| Démarrage | Secondes | Minutes |
| Taille | Mo | Go |
| Overhead | Minimal | Significatif (OS complet) |
| Sécurité | Surface d'attaque plus large | Isolation plus forte |
Quand utiliser quoi ?
- Conteneurs : microservices, CI/CD, densité maximale
- VMs : isolation forte requise, workloads Windows, legacy
Namespace PID
Grâce au namespace PID, chaque conteneur a sa propre vue des processus. Le processus principal devient PID 1.
Responsabilités du PID 1
- Reçoit les signaux : SIGTERM (
docker stop
), SIGKILL (docker kill
) - Gère les orphelins : doit faire le reaping des processus enfants
- Sa mort = arrêt du conteneur : le conteneur s'arrête quand PID 1 termine
Problème courant
Si votre application ne gère pas bien les signaux :
# Utiliser tini comme init minimaliste
docker run --init mon-image
--init
ajoute tini qui transmet correctement les signaux.
Comparaison
| Commande | Signal | Délai | Usage |
|---|---|---|---|
docker stop |
SIGTERM → SIGKILL | 10s par défaut | Arrêt propre (graceful) |
docker kill |
SIGKILL | Immédiat | Forcer l'arrêt |
Exemples
# Arrêt propre (attend jusqu'à 10s)
docker stop mon-conteneur
# Arrêt propre avec timeout personnalisé
docker stop -t 30 mon-conteneur
# Arrêt forcé immédiat
docker kill mon-conteneur
Règle
Utilisez toujours docker stop
sauf si le conteneur ne répond plus.
Principe
Chaque instruction d'un Dockerfile crée une couche (layer) :
FROM ubuntu:22.04 # Layer 1 : image de base
RUN apt-get update # Layer 2 : cache apt
RUN apt-get install nginx # Layer 3 : nginx installé
COPY app/ /var/www/ # Layer 4 : fichiers application
Les 4 avantages
| Avantage | Description | Impact |
|---|---|---|
| Partage | Layers communs partagés entre images | Économie disque |
| Cache | Layers inchangés réutilisés au build | Builds rapides |
| Téléchargement | Seuls les layers manquants téléchargés | Réseau optimisé |
| Immutabilité | Chaque layer a un hash unique | Reproductibilité |
Explication
Le layer R/W (lecture/écriture) du conteneur est éphémère. Quand vous supprimez le conteneur (docker rm
), ce layer disparaît avec toutes les données écrites.
Solutions pour persister les données
| Méthode | Usage | Commande |
|---|---|---|
| Volume nommé | Bases de données, fichiers importants | -v mydata:/var/lib/data |
| Bind mount | Développement (code source) | -v ./src:/app |
| docker commit | Sauvegarder l'état (rarement recommandé) | docker commit container image |
Exemple
# Créer un volume persistant
docker run -d -v postgres-data:/var/lib/postgresql/data postgres:15
# Les données survivent à la suppression du conteneur
docker rm -f mon-postgres
# Le volume postgres-data existe toujours !
Rôles
| Mécanisme | Rôle | Analogie |
|---|---|---|
| Namespaces | Isolent ce que le conteneur voit | Murs entre appartements |
| Cgroups | Limitent ce qu'il consomme | Compteurs d'eau/électricité |
Types de namespaces
| Namespace | Isole |
|---|---|
| PID | Processus (PID 1, 2, 3...) |
| Network | Interface réseau, IP, ports |
| Mount | Points de montage |
| UTS | Hostname |
| IPC | Mémoire partagée, sémaphores |
| User | UID/GID (rootless mode) |
Exemples cgroups
# Limiter à 50% CPU et 256 Mo RAM
docker run --cpus 0.5 --memory 256m nginx:alpine
Le problème
Toute personne ayant accès au socket Docker (/var/run/docker.sock
) peut potentiellement obtenir un accès root sur l'hôte.
Démonstration
# Un utilisateur du groupe docker peut faire ça :
docker run -v /:/hostroot -it alpine chroot /hostroot
# → Shell root sur l'hôte !
Solutions
| Solution | Description |
|---|---|
| Limiter le groupe docker | N'ajouter que les utilisateurs de confiance |
| Mode rootless | Exécuter Docker sans privilèges root |
| Podman | Alternative sans daemon, rootless par défaut |
| Docker Context | Utiliser un daemon distant sécurisé |
Signification du code 137
Le code 137 = 128 + 9 = SIGKILL
Causes possibles
docker kill
exécuté- OOM killer : le conteneur a dépassé sa limite mémoire
- Arrêt forcé du système
Diagnostic
# Voir les derniers logs
docker logs mon-conteneur
# Vérifier si OOM (Out Of Memory)
docker inspect mon-conteneur | grep -i oom
# Vérifier OOM killer dans le kernel
dmesg | grep -i "killed process"
Codes de sortie courants
| Code | Signification |
|---|---|
| 0 | Succès |
| 1-125 | Erreur application |
| 126 | Commande non exécutable |
| 127 | Commande non trouvée |
| 137 | SIGKILL (OOM ou docker kill) |
| 143 | SIGTERM (docker stop) |
