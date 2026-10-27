// Les composants de la charte (charte/composants/*) : un seul endroit pour chaque motif, aucune valeur de style.
import { h, icone } from "./dom.js";
import { ROLES, TUILES_FIXES, VERBES, fmtNombre, SEUIL_QUOTA } from "./mots.js";

export function bouton({ libelle, icon, variante = "", onclick, petit = false, disabled = false, type = "button", ...reste }) {
  return h("button", { type, class: `bouton ${variante} ${petit ? "petit" : ""}`.trim(), onclick, disabled, ...reste }, icon && icone(icon), libelle);
}

/** Un bouton de dessin seul : seulement pour le × de fermeture, le chevron de dépliage, les ports et l'envoi de l'Aide (aria-label obligatoire). */
export function boutonIcone({ icon, etiquette, onclick, classe = "" }) {
  return h("button", { type: "button", class: `bouton-icone ${classe}`.trim(), "aria-label": etiquette, onclick }, icone(icon));
}

/** La puce : choisir UNE option parmi quelques-unes visibles d'un coup. */
export function puce({ libelle, actif, onclick, disabled = false }) {
  return h("button", { type: "button", class: "puce", "aria-pressed": String(!!actif), onclick, disabled }, libelle);
}

export function groupePuces(options, valeur, onchoisir) {
  return h("div", { class: "puces", role: "group" }, options.map(([v, l]) => puce({ libelle: l, actif: v === valeur, onclick: () => onchoisir(v) })));
}

/** La case : activer ou désactiver une source dans une longue liste. */
export function caseSource({ nom, sous, actif, disabled, onclick, etat }) {
  return h(
    "button",
    { type: "button", class: "case", "aria-pressed": String(!!actif), disabled, onclick },
    h("span", { class: "case-carre", "aria-hidden": "true" }, actif ? "✓" : ""),
    h("span", { class: "case-nom" }, nom),
    sous && h("span", { class: "legende pale" }, sous),
    etat && h("span", { class: "legende pale" }, etat),
  );
}

/** Un champ : libellé au-dessus (lié par for/id), aide dessous. Rend l'élément et un lecteur de valeur (on lit AU CLIC, jamais dans un redessin). */
let compteur = 0;
export function champ({ libelle, valeur = "", aide, type = "text", placeholder = "", lignes = 0, code = false, obligatoire = false, description, autocomplete = "off" }) {
  const id = `champ-${++compteur}`;
  const saisie = lignes
    ? h("textarea", { id, rows: lignes, spellcheck: !code, class: code ? "code" : "", placeholder, value: valeur })
    : h("input", { id, type, placeholder, value: valeur, autocomplete });
  if (lignes) saisie.value = valeur;
  const el = h(
    "div",
    { class: "champ" },
    h("label", { for: id }, libelle, obligatoire && [" ", h("span", { class: "obligatoire" }, "obligatoire")]),
    saisie,
    aide && h("span", { class: "aide-champ" }, aide),
    description,
  );
  return { el, saisie, valeur: () => saisie.value, definir: (v) => (saisie.value = v) };
}

export function pastilleEtat(etat, table) {
  return h("span", { class: "etat" }, h("span", { class: `pastille ${etat}`, "aria-hidden": "true" }), h("span", {}, table[etat] || etat));
}

export function etiquetteRole(role, { auto = false } = {}) {
  const def = ROLES[role];
  const fixe = TUILES_FIXES[role];
  const nom = def ? def.nom : fixe ? fixe.sous.toUpperCase() : role;
  return h("span", { class: `role ${role} ${auto ? "auto" : ""}`.trim() }, nom); // le mot seul : 104 px ne contiennent pas le dessin de RAPPROCHER en plus
}

export function quotaVue(source) {
  if (source.etat === "off") return h("span", { class: "legende pale chiffres" }, "éteinte");
  if (source.acces === "base_exterieure") return h("span", { class: "legende chiffres", title: source.machine }, "Base extérieure"); // ni quota, ni date de copie
  if (source.copie) return h("span", { class: "legende chiffres", title: source.copie.installee ? `copie du ${source.copie.date}` : "non installée sur cette machine" }, "Copie locale"); // pas « illimité » : une copie a une date de fraîcheur
  const q = source.quota;
  if (!q) return h("span", { class: "legende pale" }, "—");
  const pct = source.pct ?? 0;
  const chaud = pct >= SEUIL_QUOTA;
  return h(
    "div",
    { class: `quota ${chaud ? "chaud" : ""}`.trim() },
    h("span", { class: "quota-texte" }, `${fmtNombre(q.utilise)} / ${fmtNombre(q.plafond)} · ${q.unite} · ${pct} %`),
    h("span", { class: "jauge", role: "img", "aria-label": `${pct} % du quota` }, h("span", { style: { width: `${pct}%` } })),
  );
}

export function carteRepliable({ titre, compte, ouverte, onbascule, corps, icon }) {
  const tete = h(
    "button",
    { type: "button", class: "carte-tete", "aria-expanded": String(!!ouverte), onclick: onbascule },
    h("span", { class: "chev" }, icone("deplier")),
    icon && icone(icon),
    h("span", { class: "titre" }, titre),
    compte && h("span", { class: "compte" }, compte),
  );
  return h("section", { class: `carte ${ouverte ? "ouverte" : ""}`.trim() }, tete, ouverte && corps);
}

// ---------------------------------------------------------------- fenêtres, panneaux, avertissements

const couches = () => document.getElementById("couches");

/** Ouvre un panneau latéral (`cote`) ou une fenêtre centrée. Rend {fermer, corps}. Échap et le voile referment (= annuler). */
export function ouvrirCouche({ cote = false, largeur = "", titre, sous, contenu, pied, surFermeture, role = "dialog" }) {
  const precedent = document.activeElement;
  const voile = h("div", { class: "voile" });
  const tete = h(
    "div",
    { class: "fenetre-tete" },
    h("div", {}, h("h2", { id: "couche-titre" }, titre), sous && h("div", { class: "fenetre-sous" }, sous)),
    boutonIcone({ icon: "fermer", etiquette: VERBES.fermer, onclick: () => fermer(true) }),
  );
  const corps = h("div", { class: "fenetre-corps" }, contenu);
  const boite = h("div", { class: cote ? `panneau ${largeur}` : `fenetre ${largeur}`, role, "aria-modal": "true", "aria-labelledby": "couche-titre" }, tete, corps, pied && h("div", { class: "fenetre-pied" }, pied));
  let ferme = false;
  function fermer(annule = false) {
    if (ferme) return;
    ferme = true;
    document.removeEventListener("keydown", touche, true);
    voile.remove();
    boite.remove();
    if (precedent && precedent.focus && document.contains(precedent)) precedent.focus();
    if (surFermeture) surFermeture(annule);
  }
  function touche(ev) {
    if (ev.key === "Escape") {
      ev.stopPropagation();
      fermer(true);
    } else if (ev.key === "Tab") {
      const cibles = [...boite.querySelectorAll("button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex='0']")].filter((e) => e.offsetParent !== null);
      if (!cibles.length) return;
      const premier = cibles[0];
      const dernier = cibles[cibles.length - 1];
      if (ev.shiftKey && document.activeElement === premier) {
        ev.preventDefault();
        dernier.focus();
      } else if (!ev.shiftKey && document.activeElement === dernier) {
        ev.preventDefault();
        premier.focus();
      }
    }
  }
  voile.addEventListener("click", () => fermer(true));
  document.addEventListener("keydown", touche, true);
  couches().append(voile, boite);
  const premiere = boite.querySelector("input, textarea, .puce, .bouton");
  (premiere || boite).focus?.();
  return { fermer, corps, boite, remplacerContenu: (c) => { corps.replaceChildren(...[c].flat()); } };
}

/** L'avertissement (charte/composants/Avertissement) : 480 px, triangle en etat-attention, le verbe exact en bouton, Annuler à côté. */
export function avertissement({ titre, points, verbe, danger = false, onconfirmer }) {
  const c = ouvrirCouche({ largeur: "w480", titre: "", role: "alertdialog", contenu: [] });
  c.boite.replaceChildren(
    h("div", { class: "avert-titre" }, icone("attention"), h("h2", { id: "couche-titre" }, titre)),
    h("ul", { class: "avert-points" }, points.map((p) => h("li", {}, p))),
    h(
      "div",
      { class: "avert-pied" },
      bouton({ libelle: verbe, variante: danger ? "danger" : "principal", onclick: () => { c.fermer(); onconfirmer(); } }),
      bouton({ libelle: VERBES.annuler, onclick: () => c.fermer(true) }),
    ),
  );
  c.boite.querySelector(".bouton")?.focus();
  return c;
}

let delaiToast = null;
/** Une phrase en bas de page qui confirme ou refuse une action ; reste lisible 6 secondes. */
export function annoncer(texte, refus = false) {
  const zone = document.getElementById("annonce");
  if (!zone) return;
  zone.replaceChildren(h("div", { class: refus ? "message-refus" : "message-lance" }, texte));
  clearTimeout(delaiToast);
  delaiToast = setTimeout(() => zone.replaceChildren(), 6000);
}
