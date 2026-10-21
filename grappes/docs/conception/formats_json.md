# Formats JSON d'entrée

Sources : `donnees/echantillons/*_1.json` (copies dans `tests/fixtures/echantillons/`), fournis par Sednal (échantillons synthétiques, archive `docs/archive/REPONSES_SEDNAL_3.md`). **Ce ne sont pas des exports réels** : valeurs inventées, structures construites d'après les documentations officielles (export Telegram Desktop, API X v2, API Instagram Graph). `web_1.json` est une **proposition de format** : il n'existe pas de standard. Tout ce qui suit reste à confirmer sur les premières vraies données collectées (voir `QUESTIONS.md`, Q16 à Q19) ; aucun export n'est attendu de Sednal.

Entrée : fichiers `.json` (objet ou liste) et `.jsonl` (un objet par ligne), UTF-8 avec ou sans BOM. Chaque fetcher défait l'enveloppe de son format (`unwrap`). Les champs absents sont tolérés sauf ceux marqués obligatoires ; un enregistrement invalide est rejeté et compté, sans interrompre le lot ; un enregistrement valide sans contenu à analyser (message de service Telegram) est compté « ignoré ». Le format plat historique (phase 1) reste accepté pour X, Telegram et web.

## Comparaison avec les fetchers de la phase 1

| Écosystème | Écart constaté | Traitement |
| --- | --- | --- |
| X | Enveloppe `{data, includes.users, meta}` ; l'auteur n'est donné que par `author_id` | `unwrap` résout `author_id` en `username` via `includes.users` ; sans correspondance : rejet « auteur introuvable » (aucune requête, aucune ré-identification) |
| X | Mentions `{username, id}` (pas `handle`) ; hashtags `{tag}` ; métriques `public_metrics.{like,retweet,reply,quote,bookmark,impression}_count` | Clés acceptées en plus de l'ancien format ; engagement = like + retweet + reply (D26) ; mention sans `username` résolue par `id` via `includes.users` si possible |
| Telegram | Export `{name, type, id, messages[]}` ; messages `id` (pas `message_id`), pas de champ `channel` | `unwrap` injecte le canal de l'export dans chaque message |
| Telegram | `type: "service"` (ex. `create_channel`) | Ignoré, compté à part |
| Telegram | `text` : chaîne **ou liste** de chaînes et d'objets `{type, text}` ; `text_entities` typées (`plain`, `link`, `mention`, `hashtag`, `text_link`...) | Texte aplati ; entités lues dans `text_entities` (à défaut `entities`, ou les objets de la liste `text`) |
| Telegram | `date` sans fuseau, `date_unixtime` en **chaîne** | `date_unixtime` préféré (UTC) ; sinon `date` lue en UTC |
| Telegram | Aucun nom public de canal dans l'export, seulement `name` ; `forwarded_from` est un nom affiché | Table d'équivalence `config/telegram.yaml` (référence) ; à défaut dérivation du nom, marquée « hypothèse » : citations conservées mais jamais validantes ; homonymes jamais fusionnés (D25, D33) |
| Instagram | Écosystème absent | `InstagramFetcher` (D26) |
| Web | `links: [{href, anchor}]` au lieu de `outlinks: [url]` ; `canonical_url`, `published_at`, `lang` en plus | `links` et `outlinks` acceptés ; `canonical_url` préférée à `url` ; `published_at` préférée à `fetched_at` |

## X (`x`)

Obligatoire : un auteur (`author_id` résolu par `includes.users`, ou `author` = `{"handle": "@x"}` / chaîne) et `id` ou `text`.

````json
{"data": [{"id": "1900000000000000001", "text": "...", "created_at": "2026-09-02T10:00:00.000Z",
           "author_id": "2000000001", "lang": "fr",
           "public_metrics": {"retweet_count": 3, "reply_count": 1, "like_count": 12},
           "entities": {"urls": [{"url": "https://t.co/a", "expanded_url": "https://..."}],
                        "mentions": [{"username": "y", "id": "2000000002"}],
                        "hashtags": [{"tag": "jardinage"}]}}],
 "includes": {"users": [{"id": "2000000001", "username": "compte_demo_a"}]},
 "meta": {"result_count": 1}}
````

* `expanded_url` préféré à `url` ; aucune résolution réseau.
* Sans `entities.mentions` / `hashtags`, extraction par regex dans le texte.
* Un « RT @compte: ... » cite `@compte` (mention) ; `referenced_tweets` et `in_reply_to_user_id` ne sont pas utilisés (Q17).
* `engagement` = likes + retweets + replies.

## Telegram (`telegram`)

Obligatoire : un canal (celui de l'export, ou `channel` sur un enregistrement plat), et `id`/`message_id` ou texte.

````json
{"name": "Canal Demo A", "type": "public_channel", "id": 1000000001,
 "messages": [
   {"id": 2, "type": "message", "date": "2026-09-02T09:15:00", "date_unixtime": "1788340500",
    "text": ["Nouvel article : ", {"type": "link", "text": "https://..."}, {"type": "mention", "text": "@y"}],
    "text_entities": [{"type": "plain", "text": "Nouvel article : "}, {"type": "link", "text": "https://..."}],
    "forwarded_from": "Canal Demo B"}]}
````

* Mentions = `@` du texte + entités `mention` + `forwarded_from`.
* Liens = entités `link` (URL dans `text`), `text_link` (URL dans `href`, à confirmer) et `url`.
* Canal : `username` s'il existe ; sinon la table d'équivalence ; sinon `name` dérivé (hypothèse). Voir D33.

## Instagram (`instagram`)

Obligatoire : `username`, et `id` ou `caption`.

````json
{"data": [{"id": "17900000000000001", "media_type": "IMAGE", "permalink": "https://www.instagram.com/p/DEMO0001/",
           "caption": "Potager avec @compte_demo_a #jardinage https://exemple-a.example.test/a",
           "timestamp": "2026-09-02T11:00:00+0000", "username": "compte_demo_c",
           "like_count": 45, "comments_count": 4}],
 "paging": {"cursors": {"before": "...", "after": "..."}, "next": "..."}}
````

* Source = `username`. Légende optionnelle (un carrousel ou une vidéo peut n'en avoir aucune).
* Mentions, hashtags et URLs extraits par regex de la légende (aucune entité structurée dans ce format).
* `children`, `media_url`, `paging` ignorés (pas de collecte, pas de pagination).
* `engagement` = `like_count` + `comments_count`.

## Web (`web`) — format proposé

Obligatoire : `canonical_url` ou `url`.

````json
{"url": "https://exemple.test/p?utm_source=a", "canonical_url": "https://exemple.test/p",
 "fetched_at": "2026-09-05T06:00:00Z", "published_at": "2026-09-02T07:00:00Z",
 "title": "...", "lang": "fr", "text": "...",
 "links": [{"href": "https://t.me/canal_demo_a", "anchor": "notre chaîne"}]}
````

* Source = domaine canonique. Texte = titre + corps.
* Liens sortants canonicalisés ; les liens vers le même domaine sont écartés.

## Liens et citations (D24, révise D14)

Un lien cite sa cible identifiable (`canon.link_target`) :

| Lien | Citation |
| --- | --- |
| `t.me/<canal>[/<id>]`, `t.me/s/<canal>` | `telegram:canal` |
| `x.com` ou `twitter.com/<compte>[/...]` | `x:compte` |
| `instagram.com/<compte>` | `instagram:compte` |
| autre site | `web:domaine` |
| `t.me/+...`, `t.me/joinchat/...`, `t.me/c/...`, `t.co/...`, `instagram.com/p/...`, `/reel/...`, `x.com/i/...`, `x.com/search` | rien |

Une invitation Telegram ou une publication Instagram ne désigne pas de compte identifiable sans résolution réseau ni ré-identification : elle ne produit plus d'entité fantôme (`web:t.me`, `web:x.com`, `web:instagram.com`). L'observation garde le lien. Un même nom dans deux écosystèmes (`x:compte_demo_a`, `telegram:compte_demo_a`) donne deux entités : aucune ré-identification.

## Identité et doublons

`obs_id` = SHA-256 tronqué de (écosystème, id natif, texte) : deux enregistrements identiques donnent le même `obs_id` et le second est compté comme doublon.
