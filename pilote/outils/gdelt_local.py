"""GDELT en copie locale, filtré France et en fenêtre glissante (document 22 §5, tranché le 27/10/2026 : pays = France, 90 jours).

    .venv/bin/python outils/gdelt_local.py [--jours 90] [--fils 6]

Pour chaque fichier GKG de 15 minutes de la fenêtre qui n'est pas encore dans la copie : téléchargement, filtre (site en « .fr » OU article en
français), puis UNE ligne par organisation citée (le champ V2Organizations seul : les champs de personnes ne sont jamais lus, règle 8). Les lignes
plus vieilles que la fenêtre sont supprimées. Reprenable : les fichiers déjà traités sont notés dans la base ; relancer complète. La base est la
même que pour les autres copies (`fichier_local`), source `gdelt-local`."""

from __future__ import annotations

import io
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "src"))

from pilote import fichier_local as fl
from pilote.config import charger

BASE = "gdelt-fr"
URLS = ("http://data.gdeltproject.org/gdeltv2/{ts}.gkg.csv.zip", "http://data.gdeltproject.org/gdeltv2/{ts}.translation.gkg.csv.zip")  # presse en anglais, puis presse traduite (le français y est)
UA = "pilote/0.1 (copie locale GDELT ; usage personnel)"
COL_SOURCE, COL_URL, COL_ORGS, COL_TRADUCTION, COL_DATE = 3, 4, 14, 25, 1  # GKG 2.1 : colonnes séparées par des tabulations


def horodatages(debut: datetime, fin: datetime) -> list[str]:
    t = debut.replace(minute=debut.minute // 15 * 15, second=0, microsecond=0)
    out = []
    while t <= fin:
        out.append(t.strftime("%Y%m%d%H%M%S"))
        t += timedelta(minutes=15)
    return out


def en_france(source: str, traduction: str) -> bool:
    return source.lower().endswith(".fr") or "srclc:fra" in traduction


def lire(ts: str) -> list[tuple] | None:
    """Les lignes (nom, source, adresse, date) des deux fichiers GKG d'un quart d'heure ; None si aucun n'existe (GDELT en saute, et publie les
    plus récents avec du retard : ils seront repris à la prochaine mise à jour, tant qu'ils ne sont pas notés comme traités)."""
    out: list[tuple] = []
    trouve = False
    for modele in URLS:
        brut = _telecharger(modele.format(ts=ts))
        if brut is None:
            continue
        trouve = True
        with zipfile.ZipFile(io.BytesIO(brut)) as z, z.open(z.namelist()[0]) as f:
            for ligne in io.TextIOWrapper(f, encoding="utf-8", errors="replace"):
                c = ligne.rstrip("\n").split("\t")
                if len(c) <= COL_TRADUCTION or not en_france(c[COL_SOURCE], c[COL_TRADUCTION]) or not c[COL_ORGS]:
                    continue
                vus = set()
                for o in c[COL_ORGS].split(";"):
                    nom = o.rsplit(",", 1)[0].strip()
                    if nom and nom.lower() not in vus:
                        vus.add(nom.lower())
                        out.append((nom, c[COL_SOURCE], c[COL_URL], c[COL_DATE][:8]))
    return out if trouve else None


def _telecharger(url: str) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for essai in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            time.sleep(3 * (essai + 1))
        except OSError:
            time.sleep(3 * (essai + 1))
    raise OSError(f"GDELT ne répond pas pour {url}")


def main(argv: list[str]) -> int:
    jours = int(argv[argv.index("--jours") + 1]) if "--jours" in argv else 90
    fils = int(argv[argv.index("--fils") + 1]) if "--fils" in argv else 6
    cfg = charger()
    cible = fl.chemin_base(cfg.dossier_copies, BASE)
    cible.parent.mkdir(parents=True, exist_ok=True)
    neuf = not cible.exists()
    con = sqlite3.connect(cible)
    con.execute("PRAGMA synchronous = OFF")
    if neuf:
        fl._schema(con)
        con.execute("CREATE TABLE fichiers (ts TEXT PRIMARY KEY)")
    maintenant = datetime.now(UTC)
    limite = maintenant - timedelta(days=jours)
    voulus = horodatages(limite, maintenant - timedelta(minutes=30))
    faits = {r[0] for r in con.execute("SELECT ts FROM fichiers")}
    a_faire = [t for t in voulus if t not in faits]
    print(f"GDELT France : {len(voulus)} fichiers dans la fenêtre de {jours} jours, {len(a_faire)} à traiter", flush=True)
    prochain = (con.execute("SELECT max(id) FROM donnees").fetchone()[0] or 0) + 1
    t0, n_lignes, i = time.time(), 0, 0
    # Par TRANCHES, et c'est le point : `pool.map` sur toute la fenêtre soumettait les ~8 600 quarts d'heure d'un coup, et les résultats
    # terminés s'empilaient en mémoire pendant que la boucle insérait ligne à ligne. Sur 90 jours, la mémoire montait sans borne. Une tranche
    # de quelques fils à la fois borne ce qui attend d'être écrit, et `executemany` écrit par lots au lieu d'un appel par ligne.
    tranche = max(fils * 4, 8)
    with ThreadPoolExecutor(fils) as pool:
        for debut in range(0, len(a_faire), tranche):
            lot_ts = a_faire[debut : debut + tranche]
            for ts, lignes in zip(lot_ts, pool.map(lire, lot_ts), strict=True):
                i += 1
                lot_d, lot_n = [], []
                for nom, source, adresse, jour in lignes or []:
                    n = fl.nom_normalise(nom)
                    if not n:
                        continue
                    lot_d.append((prochain, nom, n, "FR", "page", source, jour, f"cité dans {source} le {jour[:4]}-{jour[4:6]}-{jour[6:]} : {adresse}"))
                    lot_n.append((n, prochain))
                    prochain += 1
                    n_lignes += 1
                if lot_d:
                    con.executemany("INSERT INTO donnees(id, nom, nom_n, pays, genre, site, themes, detail) VALUES (?,?,?,?,?,?,?,?)", lot_d)
                    con.executemany("INSERT INTO noms(nom_n, donnee) VALUES (?,?)", lot_n)
                if lignes is not None and datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=UTC) < maintenant - timedelta(hours=3):  # les plus récents arrivent en retard : repris la fois suivante
                    con.execute("INSERT OR IGNORE INTO fichiers VALUES (?)", (ts,))
                if i % 96 == 0:  # un jour de traité : on valide (reprise possible)
                    con.commit()
                    print(f"  {i}/{len(a_faire)} fichiers, {n_lignes} lignes, {int(time.time() - t0)} s", flush=True)
            con.commit()  # fin de tranche : ce qui est lu est écrit, rien ne reste en attente
    # fenêtre glissante : tout ce qui est plus vieux que `jours` part
    coupe = limite.strftime("%Y%m%d")
    con.execute("DELETE FROM noms WHERE donnee IN (SELECT id FROM donnees WHERE themes < ?)", (coupe,))
    con.execute("DELETE FROM donnees WHERE themes < ?", (coupe,))
    con.execute("DROP INDEX IF EXISTS i_noms_n")
    con.execute("CREATE INDEX i_noms_n ON noms(nom_n)")
    con.execute("CREATE INDEX IF NOT EXISTS i_donnees_numero ON donnees(numero)")
    con.execute("DROP TABLE IF EXISTS fts")
    con.execute("CREATE VIRTUAL TABLE fts USING fts5(nom_n, content='noms', content_rowid='id', tokenize='unicode61 remove_diacritics 2', prefix='3')")
    con.execute("INSERT INTO fts(fts) VALUES('rebuild')")
    total = con.execute("SELECT count(*) FROM donnees").fetchone()[0]
    con.execute("DELETE FROM meta")
    con.execute("INSERT INTO meta VALUES ('lignes', ?), ('importe_le', ?), ('fenetre_jours', ?), ('fichier', 'GDELT GKG filtré France')", (str(total), time.strftime("%Y-%m-%d"), str(jours)))
    con.commit()
    con.close()
    print(f"fait : {total} lignes dans la fenêtre, {int(time.time() - t0)} s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
