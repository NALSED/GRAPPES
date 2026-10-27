"""Installe les modèles Argos pour les paires utiles (document 22) : l'anglais comme pivot, dans les deux sens, avec fr, es, de, it, ar, ru, zh."""
import sys

import argostranslate.package as p

p.update_package_index()
voulus = {("en", x) for x in ("fr", "es", "de", "it", "ar", "ru", "zh")} | {(x, "en") for x in ("fr", "es", "de", "it", "ar", "ru", "zh")}
for pk in p.get_available_packages():
    if (pk.from_code, pk.to_code) in voulus:
        print("installation", pk.from_code, "->", pk.to_code, flush=True)
        p.install_from_path(pk.download())
        voulus.discard((pk.from_code, pk.to_code))
print("manquants :", sorted(voulus))
sys.exit(1 if voulus else 0)
