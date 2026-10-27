# LibreTranslate auto-hébergé (tuile Traduction)

Installé le 27/10/2026 dans `/mnt/carte/pilote-copies/libretranslate/` (environnement Python, modèles, cache : tout sur le disque des copies, ≈ 8 Go avec les dépendances).

````
python3 -m venv venv && ./venv/bin/pip install argostranslate libretranslate
XDG_DATA_HOME=$PWD/donnees XDG_CACHE_HOME=$PWD/cache ./venv/bin/python installer_modeles.py   # fr, es, de, it, ar, ru, zh <-> en
./lancer.sh                                                                                  # écoute en 127.0.0.1:5000 seulement
````

Puis, dans `config/pilote.yaml` :

````
suite:
  traduction_url: http://127.0.0.1:5000
````

Pour démarrer au lancement de la machine : copier `libretranslate-pilote.service` dans `/etc/systemd/system/` puis `sudo systemctl enable --now libretranslate-pilote`.

Les modèles vont de et vers l'anglais ; une paire sans l'anglais (fr → es) passe par lui en deux appels, faits par `suite_traduction.traduire` (le pivot du service renvoie le texte anglais intermédiaire avec ces versions). Le processeur de la machine n'a pas AVX : les roues utilisées tournent quand même (contrôlé).
