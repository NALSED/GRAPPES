// L'assistant de première installation (fiche 02), dans la charte de la suite : mêmes quatre étapes et les mêmes routes que
// l'assistant classique (static/assistant.js) — rien n'est réinventé, seul le dessin change. Remplace tout l'écran tant que
// la configuration n'existe pas encore (`/api/suite/etat` → `premiere_installation`).
import { h } from "./dom.js";
import { apiAssistant, Refus } from "./api.js";
import { annoncer, avertissement, bouton, caseSource, champ, groupePuces, ouvrirCouche, pastilleEtat } from "./ui.js";
import { ETATS_SOURCE } from "./mots.js";

let D = null; // la réponse de GET /api/reglages (les mêmes données que l'assistant classique, pas /api/suite/etat)
let S = null;

const ETAPES = [[1, "① Sources"], [2, "② Vérification"], [3, "③ Sortie"], [4, "④ Récapitulatif"]];

/** « monde » couvre tout ; sans pays choisi, tout est proposé. */
function couvre(x, pays) {
  return !pays || x.pays.includes("monde") || x.pays.map((p) => p.toUpperCase()).includes(pays.toUpperCase());
}

function slugueur(nom) {
  return nom.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48);
}

/** Les trois états de la suite (jamais un quatrième) : un test en échec ou une source non testée restent « à vérifier ». */
function etatSuite(v) {
  return v === "ok" ? "ok" : v === "off" ? "off" : "warn";
}

function parId(id) {
  return D.parties.recherche.find((s) => s.id === id);
}

async function recharger() {
  D = await apiAssistant.reglages();
}

function echoue(e) {
  annoncer(e instanceof Refus ? e.message : "Quelque chose a échoué.", true);
}

export async function demarrerInstallation() {
  const racine = document.getElementById("app");
  try {
    D = await apiAssistant.reglages();
  } catch (e) {
    racine.replaceChildren(h("p", { class: "message-refus" }, e instanceof Refus ? e.message : "Le serveur de pilote ne répond pas."));
    return;
  }
  S = {
    etape: 1,
    e1: { pays: D.pays || "", coches: new Set(D.presets_coches || []), chercher: new Set(), plafond: D.budget.plafond_mensuel_usd },
    e2: { active: D.verification.active, mode: D.verification.mode || "memes", verifier: new Set(), initialise: false },
    e3: { actifs: new Set(D.parties.sortie.filter((f) => f.actif).map((f) => f.id)), dossier: "" },
    testResultats: {},
  };
  D.presets.forEach((p) => { if (S.e1.coches.has(p.id)) p.sources.forEach((x) => { if (x.allumee_par_defaut) S.e1.chercher.add(x.id); }); });
  dessiner();
}

function dessiner() {
  const racine = document.getElementById("app");
  racine.replaceChildren(
    h(
      "div",
      { class: "page" },
      h(
        "div",
        { class: "page-in" },
        h(
          "div",
          { class: "page-tete" },
          h("div", { class: "page-titre" }, h("h1", {}, "Installation de Grappes"), h("p", { class: "douce" }, phraseEtape())),
          groupePuces(ETAPES, S.etape, (n) => { S.etape = n; dessiner(); }),
        ),
        h("div", { class: "cartes" }, corpsEtape()),
        piedBoutons(),
      ),
    ),
  );
}

function phraseEtape() {
  if (S.etape === 1) return "Choisis où le programme va chercher. Chaque preset est un lot de sources prêtes à l'emploi pour un type de recherche.";
  if (S.etape === 2) return "Le programme recoupe chaque nom trouvé avec d'autres sources pour te dire s'il est confirmé. Tu peux la désactiver si tu préfères le brut.";
  if (S.etape === 3) return "Choisis ce que tu récupères à la fin : format et emplacement.";
  return "Voici ce qui sera utilisé. Teste chaque source avant d'entrer : tu évites de découvrir une clé fausse à la première recherche. Un test ne coûte rien.";
}

function corpsEtape() {
  if (S.etape === 1) return etape1();
  if (S.etape === 2) return etape2();
  if (S.etape === 3) return etape3();
  return etape4();
}

// ---------------------------------------------------------------- étape 1 : sources

function champPays() {
  const pp = D.pays_proposes || {};
  const autre = !!S.e1.pays && !pp[S.e1.pays];
  const sel = h(
    "select",
    { id: "inst-pays" },
    h("option", { value: "" }, "— choisis —"),
    Object.keys(pp).map((k) => h("option", { value: k, selected: k === S.e1.pays }, pp[k])),
    h("option", { value: "__autre", selected: autre }, "Un autre pays…"),
  );
  sel.value = autre ? "__autre" : S.e1.pays;
  sel.addEventListener("change", () => {
    if (sel.value !== "__autre") S.e1.pays = sel.value;
    dessiner();
  });
  const champs = [h("div", { class: "champ" }, h("label", { for: "inst-pays" }, "Ton pays"), sel)];
  if (sel.value === "__autre") {
    const f = champ({ libelle: "Code du pays (deux lettres)", valeur: S.e1.pays, placeholder: "par exemple : SE" });
    f.saisie.addEventListener("input", () => { S.e1.pays = f.valeur().trim().toUpperCase(); });
    champs.push(f.el);
  }
  return h("div", { class: "deux-col" }, champs);
}

function toutSelectionner() {
  D.presets.forEach((p) => { S.e1.coches.add(p.id); p.sources.forEach((x) => S.e1.chercher.add(x.id)); });
  dessiner();
}
function toutDeselectionner() {
  S.e1.coches.clear();
  S.e1.chercher.clear();
  dessiner();
}

function togglePreset(p) {
  if (S.e1.coches.has(p.id)) {
    S.e1.coches.delete(p.id);
    const gardees = new Set();
    D.presets.forEach((q) => { if (S.e1.coches.has(q.id)) q.sources.forEach((x) => gardees.add(x.id)); });
    p.sources.forEach((x) => { if (!gardees.has(x.id)) S.e1.chercher.delete(x.id); });
  } else {
    S.e1.coches.add(p.id);
    p.sources.forEach((x) => { if (x.allumee_par_defaut && couvre(x, S.e1.pays)) S.e1.chercher.add(x.id); });
  }
  dessiner();
}

function personnaliser(p) {
  const f = champ({ libelle: "Nom de ta copie modifiable de ce preset", valeur: "" });
  const couche = ouvrirCouche({
    largeur: "w480",
    titre: "Personnaliser un preset",
    contenu: f.el,
    pied: h(
      "div",
      { class: "pied-boutons" },
      bouton({ libelle: "Annuler", onclick: () => couche.fermer(true) }),
      bouton({
        libelle: "Enregistrer",
        variante: "principal",
        onclick: async () => {
          const nom = f.valeur().trim();
          if (!nom) return;
          try {
            await apiAssistant.presetsPersonnaliser({ depuis: p.id, nom });
            couche.fermer();
            await recharger();
            S.e1.coches.add(slugueur(nom));
            dessiner();
          } catch (e) {
            echoue(e);
          }
        },
      }),
    ),
  });
}

function ligneSourcePreset(x, pays) {
  const actif = S.e1.chercher.has(x.id);
  const sous =
    `${x.payant ? "payant" : "gratuit"}${x.cle_requise ? `, clé ${x.cle_presente ? "présente" : "absente"}` : ""}, ` +
    `${x.main === "premiere" ? "première main" : "seconde main"}, ${x.pays.includes("monde") ? "monde entier" : x.pays.join(", ")}` +
    (pays && !x.pays.includes("monde") ? (couvre(x, pays) ? " — couvre ton pays" : " — ne couvre pas ton pays") : "");
  return caseSource({ nom: x.nom, sous, actif, onclick: () => { if (actif) S.e1.chercher.delete(x.id); else S.e1.chercher.add(x.id); dessiner(); } });
}

function cartePreset(p) {
  const coche = S.e1.coches.has(p.id);
  return h(
    "section",
    { class: "carte ouverte" },
    h(
      "div",
      { class: "carte-corps" },
      caseSource({ nom: p.nom, sous: p.phrase, actif: coche, onclick: () => togglePreset(p) }),
      p.sources.length
        ? h("div", { class: "options-grille" }, p.sources.map((x) => ligneSourcePreset(x, S.e1.pays)))
        : h("p", { class: "legende pale" }, "Aucune source pour l'instant."),
      h(
        "div",
        { class: "lancer-ligne" },
        h("span", { class: "legende pale" }, `Coût : ${p.cout}`),
        bouton({ libelle: "Personnaliser à partir de ce preset", petit: true, onclick: () => personnaliser(p) }),
      ),
    ),
  );
}

function ligneCle(s) {
  const f = champ({ libelle: s.nom, type: "password", valeur: "", placeholder: "coller la clé", autocomplete: "off", description: h("span", { class: "legende" }, s.cle === "presente" ? "clé présente" : "clé absente") });
  return h(
    "div",
    { class: "lancer-ligne" },
    f.el,
    bouton({
      libelle: "Enregistrer la clé",
      petit: true,
      onclick: async () => {
        try {
          await apiAssistant.definirCle(s.cle_nom, { valeur: f.valeur() });
          f.definir("");
          await recharger();
          dessiner();
        } catch (e) {
          echoue(e);
        }
      },
    }),
  );
}

function blocCles() {
  const besoin = [...S.e1.chercher].map(parId).filter((s) => s && s.cle_requise);
  if (!besoin.length) return null;
  return h("section", { class: "carte ouverte" }, h("div", { class: "carte-corps" }, h("p", { class: "fort" }, "Clés d'API"), besoin.map(ligneCle)));
}

function ligneReglages(s) {
  const attendus = s.parametres_attendus || {};
  const champs = {};
  const noeuds = Object.keys(attendus).map((nomP) => {
    const spec = attendus[nomP] || {};
    const f = champ({ libelle: spec.libelle || nomP, valeur: (s.parametres || {})[nomP] || "", type: spec.type === "url" ? "url" : "text", obligatoire: !!spec.requis, placeholder: spec.exemple || "" });
    champs[nomP] = f;
    return f.el;
  });
  return h(
    "div",
    { class: "note" },
    h("p", { class: "fort" }, s.nom),
    h("div", { class: "deux-col" }, noeuds),
    bouton({
      libelle: "Enregistrer",
      petit: true,
      onclick: async () => {
        const parametres = {};
        Object.keys(champs).forEach((k) => { parametres[k] = champs[k].valeur(); });
        try {
          await apiAssistant.modifierSource(s.id, { parametres });
          await recharger();
          dessiner();
        } catch (e) {
          echoue(e);
        }
      },
    }),
  );
}

function blocReglages() {
  const besoin = [...S.e1.chercher].map(parId).filter((s) => s && s.parametres_attendus && Object.keys(s.parametres_attendus).length);
  if (!besoin.length) return null;
  return h("section", { class: "carte ouverte" }, h("div", { class: "carte-corps" }, h("p", { class: "fort" }, "Réglages requis"), besoin.map(ligneReglages)));
}

function champPlafond() {
  const payant = [...S.e1.chercher].map(parId).some((s) => s && s.payant);
  if (!payant) return null;
  const f = champ({ libelle: "Plafond de dépense par mois (en dollars) — tu as activé du payant", valeur: String(S.e1.plafond ?? ""), type: "number" });
  f.saisie.addEventListener("input", () => { S.e1.plafond = parseFloat(f.valeur()); });
  return f.el;
}

function etape1() {
  return [
    champPays(),
    h("div", { class: "lancer-ligne" }, bouton({ libelle: "Tout sélectionner", onclick: toutSelectionner }), bouton({ libelle: "Tout désélectionner", onclick: toutDeselectionner })),
    D.presets.map(cartePreset),
    blocCles(),
    blocReglages(),
    champPlafond(),
  ];
}

// ---------------------------------------------------------------- étape 2 : vérification

function etape2() {
  const capables = D.parties.recherche.filter((s) => s.roles.includes("verifier"));
  const eligibles = S.e2.mode === "memes" ? capables.filter((s) => S.e1.chercher.has(s.id)) : capables;
  if (!S.e2.initialise) {
    eligibles.forEach((s) => { if (s.defaut.verifier || S.e2.mode === "memes") S.e2.verifier.add(s.id); });
    S.e2.initialise = true;
  }
  return [
    h(
      "section",
      { class: "carte ouverte" },
      h(
        "div",
        { class: "carte-corps" },
        caseSource({
          nom: "Vérification",
          sous: S.e2.active ? "Vérification activée." : "Vérification désactivée : le résultat sort brut, sans confirmation.",
          actif: S.e2.active,
          onclick: () => { S.e2.active = !S.e2.active; dessiner(); },
        }),
        S.e2.active &&
          groupePuces(
            [["memes", "Vérifier seulement avec les sources déjà cochées dans Sources"], ["plus", "Activer en plus des sources de vérification seules"]],
            S.e2.mode,
            (v) => { S.e2.mode = v; S.e2.initialise = false; dessiner(); },
          ),
        S.e2.active &&
          h(
            "div",
            { class: "options-grille" },
            eligibles.length
              ? eligibles.map((s) =>
                  caseSource({
                    nom: `Utiliser « ${s.nom} » pour vérifier`,
                    sous: s.main_phrase,
                    actif: S.e2.verifier.has(s.id),
                    onclick: () => { if (S.e2.verifier.has(s.id)) S.e2.verifier.delete(s.id); else S.e2.verifier.add(s.id); dessiner(); },
                  }),
                )
              : h("p", { class: "legende pale" }, "Aucune source ne peut vérifier avec ce choix."),
          ),
      ),
    ),
  ];
}

// ---------------------------------------------------------------- étape 3 : sortie

function etape3() {
  const f = champ({ libelle: "Emplacement des fichiers (laisser vide : le dossier de chaque recherche)", valeur: S.e3.dossier, placeholder: "/chemin/vers/mes/resultats" });
  f.saisie.addEventListener("input", () => { S.e3.dossier = f.valeur(); });
  return [
    h(
      "section",
      { class: "carte ouverte" },
      h(
        "div",
        { class: "carte-corps" },
        h(
          "div",
          { class: "options-grille" },
          D.parties.sortie.map((fmt) =>
            caseSource({
              nom: fmt.nom,
              sous: fmt.description,
              actif: S.e3.actifs.has(fmt.id),
              onclick: () => { if (S.e3.actifs.has(fmt.id)) S.e3.actifs.delete(fmt.id); else S.e3.actifs.add(fmt.id); dessiner(); },
            }),
          ),
        ),
        f.el,
      ),
    ),
  ];
}

// ---------------------------------------------------------------- étape 4 : récapitulatif

async function testerUne(s) {
  S.testResultats[s.id] = { etat: "warn", phrase: "Test en cours…" };
  dessiner();
  try {
    const r = await apiAssistant.testerSource(s.id);
    S.testResultats[s.id] = { etat: etatSuite(r.statut === "ok" ? "ok" : "err"), phrase: (r.statut === "ok" ? "✓ " : "✕ ") + (r.statut === "ok" ? "" : `${r.raison} — `) + r.etat_phrase };
    return r.statut === "ok";
  } catch (e) {
    S.testResultats[s.id] = { etat: "warn", phrase: `✕ ${e instanceof Refus ? e.message : "Quelque chose a échoué."}` };
    return false;
  } finally {
    dessiner();
  }
}

async function testerTout(chois) {
  let ok = 0;
  for (const s of chois) {
    // eslint n'est pas installé ici : la boucle est volontairement séquentielle, comme l'assistant classique (un test à la fois).
    if (await testerUne(s)) ok += 1;
  }
  annoncer(`${ok} / ${chois.length} vérifiées sans problème.`);
}

function ligneRecap(s) {
  const roles = [S.e1.chercher.has(s.id) ? "cherche" : "", S.e2.active && S.e2.verifier.has(s.id) ? "vérifie" : ""].filter(Boolean).join(" et ");
  const res = S.testResultats[s.id];
  const etat = res ? res.etat : etatSuite((s.voyant && s.voyant[0]) || "off");
  const phrase = res ? res.phrase : s.etat_phrase;
  return h(
    "section",
    { class: "carte ouverte" },
    h(
      "div",
      { class: "carte-corps" },
      h(
        "div",
        { class: "lancer-ligne" },
        pastilleEtat(etat, ETATS_SOURCE),
        h("span", { class: "fort" }, s.nom),
        bouton({ libelle: "Tester", icon: "tester", petit: true, onclick: () => testerUne(s) }),
      ),
      h("p", { class: "legende pale" }, `${roles} — ${s.main_phrase}${s.cle_requise ? ` — clé ${s.cle === "presente" ? "présente" : "absente"}` : ""}`),
      h("p", { class: "legende" }, phrase),
    ),
  );
}

function etape4() {
  const chois = D.parties.recherche.filter((s) => S.e1.chercher.has(s.id) || (S.e2.active && S.e2.verifier.has(s.id)));
  const sansCle = chois.filter((s) => s.cle_requise && s.cle !== "presente");
  if (!chois.length) return [h("p", { class: "vide" }, "Aucune source choisie : retourne à l'étape ① Sources.")];
  return [
    h(
      "div",
      { class: "lancer-ligne" },
      bouton({ libelle: "Tout tester", onclick: () => testerTout(chois) }),
      sansCle.length ? bouton({ libelle: `Décocher les sources sans clé (${sansCle.length})`, onclick: () => { sansCle.forEach((s) => { S.e1.chercher.delete(s.id); S.e2.verifier.delete(s.id); }); dessiner(); } }) : null,
      bouton({ libelle: "← Retour aux sources (étape ①)", onclick: () => { S.etape = 1; dessiner(); } }),
    ),
    chois.map(ligneRecap),
  ];
}

// ---------------------------------------------------------------- navigation

function donneesEtape(n) {
  if (n === 1) return { pays: S.e1.pays, presets_coches: [...S.e1.coches], chercher: [...S.e1.chercher], plafond: Number.isNaN(S.e1.plafond) ? undefined : S.e1.plafond };
  if (n === 2) return { active: S.e2.active, mode: S.e2.mode, verifier: [...S.e2.verifier] };
  return { actifs: [...S.e3.actifs], dossier: S.e3.dossier };
}

/** Avant d'activer une source payante ou à risque, son avertissement se lit une fois ; sur confirmation, la même demande
 *  repart avec `confirme: true` (même mécanique qu'à l'allumage d'une source depuis Réglages › Sources). */
function avecConfirmation(appel) {
  return appel(false).catch((e) => {
    if (e instanceof Refus && e.statut === 409 && e.corps && e.corps.avertissements) {
      return new Promise((resolve, reject) => {
        avertissement({
          titre: "Avant d'activer ces sources",
          points: e.corps.avertissements.map((a) => `${a.nom} : ${a.texte}`),
          verbe: "Confirmer",
          onconfirmer: () => appel(true).then(resolve, reject),
        });
      });
    }
    throw e;
  });
}

async function suivant() {
  if (S.etape < 4) {
    S.etape += 1;
    dessiner();
    return;
  }
  try {
    await avecConfirmation((confirme) => apiAssistant.terminer({ etape1: donneesEtape(1), etape2: donneesEtape(2), etape3: donneesEtape(3), confirme }));
    location.reload();
  } catch (e) {
    echoue(e);
  }
}

function piedBoutons() {
  return h(
    "div",
    { class: "pied-boutons" },
    S.etape > 1 ? bouton({ libelle: "← Précédent", onclick: () => { S.etape -= 1; dessiner(); } }) : null,
    h("span", { class: "droite" }, bouton({ libelle: S.etape === 4 ? "Terminer et entrer dans le menu" : "Suivant →", variante: "principal", onclick: suivant })),
  );
}
