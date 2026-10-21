# Modèles de données

Référence : `src/grappes/models.py` (dataclasses immuables, `slots=True`).

* `SourceRef(ecosystem, ident)` : clé canonique `ecosystem:ident`.
* `Observation` : contenu normalisé ; `obs_id` stable, `ts` UTC ou `None`, `mentions`, `links` (URLs canonicalisées), `hashtags` (minuscules), `engagement` >= 0.
* `Entity`, `Lexicon`, `Grappe` : conformes à MISSION §7.

## Canonicalisation (`canon.py`)

* Handle : minuscules, sans `@`.
* Domaine : hôte seul, minuscules, sans `www.` ni port.
* URL : schéma et hôte en minuscules, sans `www.`, `utm_*`, `fbclid`, fragment ni `/` final ; casse du chemin conservée ; idempotente.
