// La fenêtre Aide (spécification 11) : un outil dans l'outil. Elle APPELLE DES FONCTIONS et met en forme ce qu'elles rendent ; elle n'écrit
// aucun fait. Tous les noms de source, de tuile et d'option affichés ici viennent d'un retour de fonction (le serveur), jamais d'un texte écrit
// dans ce fichier ni d'un modèle. Sans modèle, les trois puces marchent : seule la phrase libre est grisée.
import { api, Refus } from "./api.js";
import { h, icone } from "./dom.js";
import { app } from "./etat.js";
import { VERBES, aPluriel } from "./mots.js";
import { bouton, boutonIcone, etiquetteRole } from "./ui.js";
import { plan, poserProposition, selectionner, viderSauvegarde } from "./plan.js";

const INTRO = "Je connais tes sources, tes outils et ton plan de travail. Je ne cherche pas à ta place : je te dis quoi poser, et pourquoi.";
const PUCES = ["Comment je fais…", "Pourquoi ça n'a rien donné ?", "Ça veut dire quoi…"];
const cle = "grappes.aide.ouverte";

const etatAide = { ouverte: lireOuverte(), messages: [] };
let racine = null;

function lireOuverte() {
  try { return localStorage.getItem(cle) !== "non"; } catch { return true; }
}
function noterOuverte() {
  try { localStorage.setItem(cle, etatAide.ouverte ? "oui" : "non"); } catch { /* stockage indisponible : l'état reste en mémoire */ }
}

export function monterAide() {
  racine = document.getElementById("aide");
  dessiner();
}
export const redessinerAide = () => racine && dessiner();

const pousser = (m) => { etatAide.messages.push(m); dessiner(); const fil = racine.querySelector(".aide-fil"); if (fil) fil.scrollTop = fil.scrollHeight; };
const dire = (texte) => pousser({ type: "r", texte });
const demander = (texte) => pousser({ type: "q", texte });
const refus = (e) => dire(e instanceof Refus ? e.message : "Quelque chose a échoué.");

async function comment() {
  demander(PUCES[0]);
  try {
    const { objectifs } = await api.aideGet("objectifs");
    pousser({ type: "choix", titre: "Pour quoi faire ?", options: objectifs.map((o) => ({ libelle: o.phrase.replace(/\.$/, ""), agir: () => proposer(o) })) });
  } catch (e) { refus(e); }
}
async function proposer(o) {
  demander(o.phrase);
  const pays = ["FR", "UK", "US", "UE"].includes(app.data.simple.pays) ? app.data.simple.pays : null;
  try {
    afficherProposition(await api.aide("proposer_plan", { objectif: o.id, pays }));
  } catch (e) { refus(e); }
}
function afficherProposition(prop) {
  if (prop.vide) {
    dire("Aucune source allumée de cette catégorie ne correspond. Allume-en une dans Réglages › Sources, puis redemande-moi.");
    pousser({ type: "ouvrir", ecran: "reglages/sources" });
    return;
  }
  pousser({ type: "plan", prop, etat: "propose" });
}
async function pourquoi() {
  demander(PUCES[1]);
  try {
    await viderSauvegarde();
    const res = await api.aide("verifier_plan", { saisie: plan().saisie || "" });
    pousser({ type: "constats", constats: res.constats, langue: res.langue_saisie, saisie: !!(plan().saisie || "").trim() });
  } catch (e) { refus(e); }
}
async function definirChoix() {
  demander(PUCES[2]);
  try {
    const { mots } = await api.aideGet("mots");
    pousser({ type: "choix", titre: "Quel mot ?", options: mots.map((m) => ({ libelle: m, agir: () => definir(m) })) });
  } catch (e) { refus(e); }
}
async function definir(mot) {
  demander(mot);
  try {
    const d = await api.aide("definir", { mot });
    pousser({ type: "def", mot: d.mot, definition: d.definition });
  } catch (e) { refus(e); }
}
async function phrase(texte) {
  demander(texte);
  try {
    const r = await api.aide("phrase", { phrase: texte });
    if (!r.modele) { dire("Le modèle n'est pas disponible. Les trois boutons du bas marchent sans lui."); return; }
    if (!r.fonction) { dire("Je n'ai pas compris cette phrase. Essaie un des trois boutons du bas."); return; }
    if (r.refus) { dire(r.refus); return; }
    const x = r.resultat;
    if (r.fonction === "proposer_plan") afficherProposition(x);
    else if (r.fonction === "verifier_plan") pousser({ type: "constats", constats: x.constats, langue: null, saisie: false });
    else if (r.fonction === "definir") pousser({ type: "def", mot: x.mot, definition: x.definition });
    else if (r.fonction === "ouvrir") pousser({ type: "ouvrir", ecran: x.ecran });
    else if (r.fonction === "lister_sources") pousser({ type: "liste", titre: aPluriel(x.sources.length, "source", "sources"), lignes: x.sources.map((s) => [s.nom, s.role]) });
    else if (r.fonction === "lire_plan") pousser({ type: "liste", titre: aPluriel(x.tuiles.length, "tuile", "tuiles") + " sur le plan", lignes: x.tuiles.map((t) => [t.nom, t.role]) });
  } catch (e) { refus(e); }
}

// ---------------------------------------------------------------- dessin

function message(m, i) {
  if (m.type === "q") return h("div", { class: "bulle-q" }, m.texte);
  if (m.type === "r") return h("div", { class: "bulle-r" }, m.texte);
  if (m.type === "def") return h("div", { class: "bulle-r" }, h("span", { class: "fort" }, m.mot), " — ", m.definition); // la définition est celle de la liste close, mot pour mot
  if (m.type === "choix") return h("div", { class: "bulle-r" }, h("p", { class: "legende" }, m.titre), h("div", { class: "aide-choix" }, m.options.map((o) => h("button", { type: "button", class: "aide-puce", onclick: o.agir }, o.libelle))));
  if (m.type === "liste") return h("div", { class: "aide-carte" }, h("span", { class: "etiquette-col" }, m.titre), m.lignes.map(([nom, role]) => h("div", { class: "aide-tuile" }, h("span", { class: "trait" }), h("span", { class: "nom" }, nom), etiquetteRole(role, { auto: true }))));
  if (m.type === "ouvrir") return h("div", { class: "bulle-r" }, bouton({ libelle: m.ecran.split("/").pop(), petit: true, onclick: () => app.naviguer(m.ecran) }));
  if (m.type === "plan") {
    const fini = m.etat !== "propose";
    return h("div", { class: "aide-carte" },
      h("span", { class: "etiquette-col" }, m.prop.titre),
      m.prop.tuiles.map((t) => h("div", { class: "aide-tuile" }, h("span", { class: "trait" }), h("span", { class: "nom" }, t.nom), etiquetteRole(t.role, { auto: true }))),
      fini
        ? h("p", { class: "legende" }, m.etat === "pose" ? "Tuiles posées sur le plan. Les liens sont à toi : relie-les." : "Proposition annulée.")
        : h("div", { class: "aide-boutons" },
          bouton({ libelle: "Poser ces tuiles", variante: "principal", petit: true, onclick: () => { const n = poserProposition(m.prop); m.etat = "pose"; m.posees = n; app.rendre(); dessiner(); } }), // l'Aide ne pose rien d'elle-même : c'est ce bouton qui pose
          bouton({ libelle: VERBES.annuler, petit: true, onclick: () => { m.etat = "annule"; dessiner(); } })));
  }
  if (m.type === "constats") {
    if (!m.constats.length) return h("div", { class: "bulle-r" }, "Je ne vois rien à signaler dans le plan. Je ne juge pas le contenu des grappes : si un résultat te paraît faux, ce n'est pas d'ici que ça se vérifie.");
    return h("div", { class: "aide-carte" },
      m.constats.map((c) => h("button", { type: "button", class: `constat ${c.niveau}`, onclick: () => { app.naviguer("recherche/avancee"); selectionner(c.tuile); } },
        h("span", { class: "point", "aria-hidden": "true" }), h("span", {}, h("span", { class: "fort" }, c.nom), " ", c.texte), h("span", { class: "niveau" }, c.niveau))),
      m.saisie && !m.langue && h("p", { class: "legende" }, "La langue de ta saisie n'a pas pu être détectée : je n'ai pas contrôlé les langues des sources."),
      !m.saisie && h("p", { class: "legende" }, "Le plan n'a pas de saisie : je n'ai pas contrôlé les langues des sources."));
  }
  return null;
}

function dessiner() {
  if (!racine) return;
  const modele = !!app.data?.modele;
  racine.replaceChildren();
  if (!etatAide.ouverte) {
    racine.append(h("button", { type: "button", class: "aide-replie", "aria-label": `${VERBES.deplier} l'Aide`, onclick: () => { etatAide.ouverte = true; noterOuverte(); dessiner(); } },
      h("span", { class: "picto aide-picto" }, icone("aide")), h("span", { class: "titre" }, "Aide"), h("span", { class: "chev" }, icone("deplier"))));
    return;
  }
  const saisie = h("input", { type: "text", placeholder: "Pose ta question…", disabled: !modele, "aria-label": "Pose ta question", title: modele ? "" : "La phrase libre demande un modèle, qui n'est pas disponible. Les trois boutons marchent sans lui." });
  const envoyer = () => { const t = saisie.value.trim(); if (t) { saisie.value = ""; phrase(t); } };
  saisie.addEventListener("keydown", (ev) => { if (ev.key === "Enter") envoyer(); });
  const envoi = boutonIcone({ icon: "lancer", etiquette: "Envoyer", onclick: envoyer, classe: "envoyer" });
  envoi.disabled = !modele;
  racine.append(h("aside", { class: "aide", role: "complementary", "aria-label": "Aide" },
    h("div", { class: "aide-tete" }, h("span", { class: "picto aide-picto" }, icone("aide")), h("span", { class: "titre" }, "Aide"),
      boutonIcone({ icon: "deplier", etiquette: VERBES.replier, onclick: () => { etatAide.ouverte = false; noterOuverte(); dessiner(); } })),
    h("div", { class: "aide-fil", "aria-live": "polite" }, h("p", { class: "aide-intro" }, INTRO, !modele && " La phrase libre est grisée : elle demande un modèle, qui n'est pas disponible. Les trois boutons marchent sans lui."), etatAide.messages.map(message)),
    h("div", { class: "aide-pied" },
      h("div", { class: "aide-puces" }, [[PUCES[0], comment], [PUCES[1], pourquoi], [PUCES[2], definirChoix]].map(([l, f]) => h("button", { type: "button", class: "aide-puce", onclick: f }, l))),
      h("div", { class: "aide-saisie" }, saisie, envoi))));
}
