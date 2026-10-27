// La liste close des mots de grappes (charte/nommage.md), centralisée comme les jetons : tout libellé affiché vient d'ici. Si un écran
// a besoin d'un mot absent, c'est charte/nommage.md puis cette table qu'on modifie d'abord, jamais l'écran.

export const ONGLETS = [
  { id: "tableau-de-bord", nom: "Tableau de bord", icone: "tableau-de-bord", concu: false },
  { id: "recherche", nom: "Recherche", icone: "recherche", concu: true },
  { id: "reglages", nom: "Réglages", icone: "reglages", concu: true },
  { id: "tri", nom: "Tri", icone: "tri", concu: true },
];

export const PLUS_TARD = "plus tard";

// Deux tables d'états : au féminin pour une source, au masculin pour un outil (un seul tableau avait fait afficher « opérationnelle » sur un outil).
export const ETATS_SOURCE = { ok: "opérationnelle", warn: "à vérifier", off: "éteinte" };
export const ETATS_OUTIL = { ok: "opérationnel", warn: "à vérifier", off: "éteint" };

export const ROLES = {
  CHERCHER: { nom: "CHERCHER", icone: "chercher" },
  VERIFIER: { nom: "VÉRIFIER", icone: "verifier" },
  ENRICHIR: { nom: "ENRICHIR", icone: "enrichir" },
  CATALOGUE: { nom: "CATALOGUE", icone: "catalogue" },
  OUTIL: { nom: "OUTIL", icone: "outil" },
  RAPPROCHER: { nom: "RAPPROCHER", icone: "rapprocher" },
};
export const ROLES_ORDRE = ["CHERCHER", "VERIFIER", "ENRICHIR", "CATALOGUE", "OUTIL", "RAPPROCHER"];
export const ROLES_OUTIL = ["OUTIL", "RAPPROCHER", "CATALOGUE"];
// Les deux tuiles sans rôle : « Ta saisie » (le départ) et « Grappes » (l'arrivée).
export const TUILES_FIXES = {
  ENTREE: { nom: "Ta saisie", icone: "saisie", sous: "départ" },
  GRAPPES: { nom: "Grappes", icone: "grappe", sous: "résultat" },
};

export const VERBES = {
  ajouter: "Ajouter", modifier: "Modifier", enregistrer: "Enregistrer", annuler: "Annuler", fermer: "Fermer", allumer: "Allumer",
  eteindre: "Éteindre", retirer: "Retirer", supprimer: "Supprimer", lancer: "Lancer", reutiliser: "Réutiliser", confirmer: "Confirmer", separer: "Séparer",
  remettre: "Remettre par défaut", ranger: "Ranger", filtrer: "Filtrer", replier: "Replier", deplier: "Déplier",
};

export const COUTS = ["gratuit", "payant"];
// Fiabilité de la source : code Admiralty, axe A–F (spécification 05). Une phrase sous les puces, pas six à la fois.
export const FIABILITES = [
  ["A", "A — Entièrement fiable : source officielle, recoupée, sans historique d'erreur."],
  ["B", "B — Fiable d'habitude : source établie, erreurs rares et corrigées."],
  ["C", "C — Assez fiable : source correcte mais déjà en défaut par le passé."],
  ["D", "D — Pas toujours fiable : source irrégulière, à recouper systématiquement."],
  ["E", "E — Non fiable : source peu fondée ou orientée."],
  ["F", "F — Fiabilité indéterminée : pas assez d'historique pour juger."],
];
export const fiabiliteParDefaut = (cat) => (cat === "web" || cat === "presse" ? "D" : "B");
export const EFFETS = [
  ["rien", "Rien", "L'outil travaille en silence."],
  ["compteur", "Compteur", "Le Tableau de bord affiche un chiffre : combien de résultats entrent et combien sortent."],
  ["journal", "Journal", "Chaque passage ajoute une ligne dans le journal du Tableau de bord."],
  ["alerte", "Alerte", "Le Tableau de bord affiche une alerte quand l'outil le décide (budget, quota…)."],
];
export const PAYS = ["Tous", "FR", "UK", "US", "UE"];
export const SEUIL_QUOTA = 80;

// Ce que la Recherche simple dit de chaque préréglage (maquette Recherche.dc.html) : [phrase, ce qu'on saisit].
export const PRESETS_INFO = {
  entreprises: ["Trouve une entreprise dans les registres.", "nom de l'entreprise"],  // règle 8 : une entreprise, jamais une recherche par nom de personne physique
  assos: ["Trouve une association dans les registres officiels.", "nom de l'association"],
  orgs: ["Trouve une administration ou un organisme public.", "nom de l'organisme"],
  web: ["Cherche sur le web ouvert.", "mots à chercher"],
  rs: ["Cherche des groupes et des événements sur les réseaux ouverts.", "nom, mot-clé ou hashtag"],
  lieux: ["Trouve et localise un lieu.", "nom ou adresse du lieu"],
  presse: ["Cherche dans la presse et les médias.", "nom, sujet ou média"],
  perso: ["Tes sources et scripts à toi.", "ce que ton script attend"],
};

// Ce que reçoit et renvoie chaque rôle de tuile, pour la fenêtre d'une tuile (maquette Recherche.dc.html).
export const ES_ROLE = {
  ENTREE: [null, "Le texte saisi, avec le pays."],
  CHERCHER: ["Le nom saisi.", "Des fiches : nom, identifiant, adresse, source."],
  VERIFIER: ["Des fiches à confirmer.", "Les mêmes fiches, marquées confirmées ou non."],
  ENRICHIR: ["Des fiches.", "Les fiches avec des informations en plus (adresse, coordonnées)."],
  CATALOGUE: ["Rien de précis.", "Une liste de sources proposées."],
  OUTIL: ["Des fiches.", "Les fiches après le traitement de l'outil."],
  RAPPROCHER: ["Des fiches de plusieurs sources.", "Les fiches rassemblées, doublons retirés."],
  GRAPPES: ["Les fiches regroupées.", null],
};
export const EFFET_DE_ROLE = {
  CHERCHER: "Dans le Tableau de bord : nombre de résultats trouvés par cette source.",
  VERIFIER: "Dans le Tableau de bord : nombre de confirmations apportées.",
  ENRICHIR: "Dans le Tableau de bord : informations ajoutées aux résultats.",
  CATALOGUE: "Dans le Tableau de bord : sources proposées par ce catalogue.",
  ENTREE: "Ce que tu saisis au lancement.",
  GRAPPES: "Les résultats regroupés arrivent ici.",
};

export const AVERTISSEMENT_IA = [
  "Ce que cette tuile produit ne vient d'aucune source : c'est une IA qui l'écrit.",
  "Le résultat peut changer d'un lancement à l'autre, avec la même question et les mêmes données.",
  "Une IA peut écrire quelque chose de faux avec assurance. Rien de ce qu'elle produit ne compte comme un fait vérifié.",
  "Tout ce qui sort de cette tuile est marqué « IA » dans la grappe, et le reste à chaque étape.",
];

export const MARQUE_IA = "IA";
export const NIVEAUX = { bloquant: "bloquant", remarque: "remarque" };

export function fmtNombre(n) {
  return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/** « 22/10 · 18:30 », ou « Aujourd'hui · 09:12 » / « Hier · 16:40 », en heure locale. */
export function fmtDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p2 = (n) => String(n).padStart(2, "0");
  const hm = `${p2(d.getHours())}:${p2(d.getMinutes())}`;
  const auj = new Date();
  const jours = Math.round((new Date(auj.getFullYear(), auj.getMonth(), auj.getDate()) - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
  if (jours === 0) return `Aujourd'hui · ${hm}`;
  if (jours === 1) return `Hier · ${hm}`;
  return `${p2(d.getDate())}/${p2(d.getMonth() + 1)} · ${hm}`;
}

export const aPluriel = (n, un, plusieurs) => `${n} ${n > 1 ? plusieurs : un}`;

// Ce que le moteur actuel fait de la recherche (QUESTIONS suite-2) : dit en clair plutôt que laissé à deviner.
export const AVIS_MOTEUR = "Le moteur obéit au plan : seules les sources reliées de « Ta saisie » à « Grappes » partent, une vérification ne juge que les sources placées avant elle, et Filtre, Condition « si », Traduction, Format et les scripts sont joués. Boucle, Attente, Compteur budget, Assistant IA et RSSHub ne le sont pas encore : un lancement le dit.";

// Onglet Tri (spécification 16).
export const TRI = {
  vide: "Aucun rapprochement à examiner. Fusion/doublons n'a rien trouvé de nouveau depuis la dernière recherche.",
  tranches: "Déjà tranchés",
  confirme: "Confirmé",
  separe: "Séparé",
  absent: "— absent —",
  indisponible: "Le moteur de rapprochement n'a pas pu tourner : relis le journal de la recherche.",
};
export const compteRapprochements = (n) => `${n} rapprochement${n > 1 ? "s" : ""} à examiner, du plus incertain au plus certain.`;
