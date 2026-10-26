// Plan de travail (spécification 08) : un canevas libre. On pose les tuiles d'abord, on tire les liens ensuite, jamais de lien automatique.
// Le modèle de données tient en deux listes : nodes [{id, nom, role, x, y, removable, opts, cat?, ref?}] et edges [{id, from, to}].
import { api } from "./api.js";
import { h, icone, svg } from "./dom.js";
import { agir, app, outilParId, sourceParId } from "./etat.js";
import { EFFET_DE_ROLE, ES_ROLE, ETATS_OUTIL, ETATS_SOURCE, MARQUE_IA, ROLES, TUILES_FIXES, VERBES } from "./mots.js";
import { annoncer, bouton, boutonIcone, champ, etiquetteRole, ouvrirCouche, puce } from "./ui.js";

const TUILE = 64;
const PORT = 7; // demi-largeur d'un port : son centre est sur le bord de la tuile
const OPTIONS_SOURCE = [["Résultats maximum", "50"], ["Si la source échoue", "continuer"]];
let zone = null; // {toile, interieur, svg, noeuds: Map, liens: Map}
let drag = null;
let delaiSauvegarde = null;
let fenetreTuile = null;

export const plan = () => app.data.plan;
const noeud = (id) => plan().nodes.find((n) => n.id === id);

let enAttente = false;
function envoyer() {
  enAttente = false;
  const p = plan();
  return api.put("/plan", { nodes: p.nodes, edges: p.edges, cats: p.cats, saisies: p.saisies, saisie: p.saisie }).catch((e) => annoncer(e.message, true));
}
function sauvegarder() {
  clearTimeout(delaiSauvegarde);
  enAttente = true;
  delaiSauvegarde = setTimeout(envoyer, 250);
}
/** Avant toute question au serveur sur le plan (l'Aide, le lancement) : ce qu'il lit doit être ce qui est à l'écran. */
export async function viderSauvegarde() {
  if (!enAttente) return;
  clearTimeout(delaiSauvegarde);
  await envoyer();
}

/** Un plan neuf contient seulement « Ta saisie » et « Grappes », non reliées : c'est l'utilisateur qui relie. */
export function initialiserPlan() {
  const p = plan();
  if (p.nodes.length) return;
  p.nodes.push({ id: "saisie", nom: TUILES_FIXES.ENTREE.nom, role: "ENTREE", x: 40, y: 150, removable: false, opts: [["Ce que tu cherches", "la saisie de la recherche"], ["Pays", "Tous"]] });
  p.nodes.push({ id: "grappes", nom: TUILES_FIXES.GRAPPES.nom, role: "GRAPPES", x: 640, y: 150, removable: false, opts: [] });
  sauvegarder();
}

function emplacementLibre() {
  for (let y = 50; y < 1400; y += 130) {
    for (let x = 40; x < 1100; x += 170) {
      if (plan().nodes.every((n) => Math.abs(n.x - x) > 120 || Math.abs(n.y - y) > 115)) return [x, y];
    }
  }
  return [40, 50];
}

export function poserBrique(def) {
  const [x, y] = emplacementLibre();
  const n = { ...def, x, y, removable: true };
  if (plan().nodes.some((m) => m.id === n.id)) return null;
  plan().nodes.push(n); // posée SANS lien
  if (n.cat && !plan().cats.includes(n.cat)) plan().cats.push(n.cat);
  app.recherche.selection = n.id;
  app.recherche.lienChoisi = null;
  sauvegarder();
  dessinerToile();
  return n;
}

export function briqueSource(s) {
  return { id: `${s.cat}:${s.id}`, nom: s.nom, role: s.role, ref: s.id, cat: s.cat, opts: OPTIONS_SOURCE.map((p) => [...p]) };
}
export function briqueOutil(o) {
  return { id: `${o.id}:${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`, nom: o.nom, role: o.role, ref: o.id, opts: o.options.map((p) => [...p]) };
}

/** RETIRER une tuile : elle sort du plan avec ses liens, rien n'est effacé ailleurs (la source reste dans Réglages). */
export function retirerTuile(id) {
  const n = noeud(id);
  if (!n || !n.removable) return;
  plan().nodes = plan().nodes.filter((m) => m.id !== id);
  plan().edges = plan().edges.filter((e) => e.from !== id && e.to !== id);
  if (app.recherche.selection === id) app.recherche.selection = null;
  app.recherche.lien = null;
  sauvegarder();
  dessinerToile();
}

function ajouterLien(a, b) {
  const A = noeud(a);
  const B = noeud(b);
  if (!A || !B || a === b || B.role === "ENTREE" || A.role === "GRAPPES") return false;
  if (plan().edges.some((e) => e.from === a && e.to === b)) return false;
  plan().edges.push({ id: `${a}>${b}`, from: a, to: b });
  sauvegarder();
  return true;
}
/** La sortie « oui » ou « non » d'une condition : sans elle le moteur ne sait pas quelle branche garder. */
function etiqueterLien(id, label) {
  const e = plan().edges.find((x) => x.id === id);
  if (!e) return;
  if (label) e.label = label;
  else delete e.label;
  sauvegarder();
}
const genreDe = (n) => {
  const o = n.ref && outilParId(n.ref);
  return o && o.nature !== "script" ? o.modele || o.id : null;
};

function retirerLien(id) {
  plan().edges = plan().edges.filter((e) => e.id !== id);
  if (app.recherche.lienChoisi === id) app.recherche.lienChoisi = null;
  sauvegarder();
}

/** RANGER : replace les tuiles en colonnes par profondeur, sans toucher à aucun lien. */
export function ranger() {
  const base = { ENTREE: 0, CHERCHER: 1, CATALOGUE: 1, OUTIL: 1, VERIFIER: 2, ENRICHIR: 3, RAPPROCHER: 4, GRAPPES: 0 };
  const prof = {};
  plan().nodes.forEach((n) => (prof[n.id] = base[n.role] ?? 1));
  for (let i = 0; i < plan().nodes.length; i++) {
    let change = false;
    for (const e of plan().edges) {
      if (e.to === "grappes" || prof[e.from] === undefined || prof[e.to] === undefined) continue;
      if (prof[e.to] <= prof[e.from]) { prof[e.to] = prof[e.from] + 1; change = true; }
    }
    if (!change) break;
  }
  const max = Math.max(0, ...plan().nodes.filter((n) => n.role !== "GRAPPES").map((n) => prof[n.id]));
  prof.grappes = max + 1;
  const colonnes = {};
  [...plan().nodes].sort((a, b) => a.y - b.y).forEach((n) => ((colonnes[prof[n.id]] ||= []).push(n.id)));
  plan().nodes.forEach((n) => { n.x = 40 + prof[n.id] * 170; n.y = 50 + colonnes[prof[n.id]].indexOf(n.id) * 130; });
  sauvegarder();
  dessinerToile();
}

const courbe = (x1, y1, x2, y2) => {
  const dx = Math.max(40, Math.abs(x2 - x1) / 2);
  return `M${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`;
};
const sortieDe = (n) => [n.x + TUILE, n.y + TUILE / 2];
const entreeDe = (n) => [n.x, n.y + TUILE / 2];

function pointToile(ev) {
  const r = zone.interieur.getBoundingClientRect();
  return [ev.clientX - r.left, ev.clientY - r.top];
}

// ---------------------------------------------------------------- la toile

export function toile() {
  const interieur = h("div", { class: "toile-in" });
  const t = h("div", { class: "toile", role: "application", "aria-label": "Plan de travail", "data-cv": "" }, interieur);
  zone = { toile: t, interieur, svg: null, noeuds: new Map(), liens: new Map(), temp: null, boutonLien: null };
  t.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest(".tuile-bloc, .lien-retrait")) return;
    if (ev.target.classList.contains("lien-cible")) return;
    app.recherche.selection = null; app.recherche.lienChoisi = null; app.recherche.lien = null;
    dessinerToile();
  });
  t.addEventListener("pointermove", (ev) => {
    if (drag) deplacer(ev);
    else if (app.recherche.lien && zone.temp) majTemp(ev);
  });
  dessinerToile();
  return t;
}

function tailleToile() {
  const maxX = Math.max(0, ...plan().nodes.map((n) => n.x));
  const maxY = Math.max(0, ...plan().nodes.map((n) => n.y));
  zone.interieur.style.width = `${Math.max(980, maxX + 220)}px`;
  zone.interieur.style.height = `${Math.max(420, maxY + 150)}px`;
}

export function dessinerToile() {
  if (!zone) return;
  tailleToile();
  const { interieur } = zone;
  interieur.replaceChildren();
  zone.noeuds = new Map();
  zone.liens = new Map();
  zone.svg = svg("svg", { class: "liens", "aria-hidden": "true" });
  interieur.append(zone.svg);
  for (const e of plan().edges) {
    const A = noeud(e.from);
    const B = noeud(e.to);
    if (!A || !B) continue;
    const choisi = app.recherche.lienChoisi === e.id;
    const d = courbe(...sortieDe(A), ...entreeDe(B));
    const trait = svg("path", { class: `lien-trait ${choisi ? "choisi" : ""}`.trim(), d });
    const cible = svg("path", { class: "lien-cible", d });
    cible.addEventListener("pointerdown", (ev) => {
      ev.stopPropagation();
      app.recherche.lienChoisi = e.id; app.recherche.selection = null; app.recherche.lien = null;
      dessinerToile();
    });
    zone.svg.append(trait, cible);
    zone.liens.set(e.id, [trait, cible]);
    if (e.label) {
      const [x1, y1] = sortieDe(A);
      const mot = svg("text", { class: "lien-etiquette", x: x1 + 10, y: y1 - 6 });
      mot.textContent = e.label;
      zone.svg.append(mot);
    }
  }
  zone.temp = svg("path", { class: "lien-temp cache", d: "M0 0" });
  zone.svg.append(zone.temp);
  for (const n of plan().nodes) {
    const bloc = blocTuile(n);
    zone.noeuds.set(n.id, bloc);
    interieur.append(bloc);
  }
  const choisi = plan().edges.find((e) => e.id === app.recherche.lienChoisi);
  if (choisi) {
    const A = noeud(choisi.from);
    const B = noeud(choisi.to);
    if (A && B) {
      const [x1, y1] = sortieDe(A);
      const [x2, y2] = entreeDe(B);
      const b = bouton({ libelle: `${VERBES.retirer} le lien`, icon: "retirer", variante: "danger", petit: true, onclick: () => { retirerLien(choisi.id); dessinerToile(); } });
      b.classList.add("lien-retrait");
      b.style.left = `${Math.round((x1 + x2) / 2 - 64)}px`;
      b.style.top = `${Math.round((y1 + y2) / 2 - 15)}px`;
      b.addEventListener("pointerdown", (ev) => ev.stopPropagation());
      interieur.append(b);
    }
  }
  if (plan().nodes.length <= 2 && !plan().edges.length) {
    interieur.append(h("p", { class: "toile-vide", style: { position: "absolute", left: "260px", top: "150px", width: "260px" } }, "Pose des briques depuis la palette, puis relie-les : appuie sur le port de sortie d'une tuile, puis clique une autre tuile."));
  }
}

function blocTuile(n) {
  const fixe = TUILES_FIXES[n.role];
  const choisie = app.recherche.selection === n.id;
  const armee = app.recherche.lien === n.id;
  const roleIcone = fixe ? fixe.icone : ROLES[n.role].icone;
  const portSortie = n.role !== "GRAPPES" && h("button", {
    type: "button", class: `port sortie ${armee ? "armee" : ""}`.trim(), "aria-label": `Sortie de ${n.nom} : tire un lien`,
    onpointerdown: (ev) => { ev.stopPropagation(); ev.preventDefault(); app.recherche.lien = armee && !ev.pointerType.startsWith("mouse") ? null : n.id; app.recherche.lienChoisi = null; app.recherche.selection = n.id; dessinerToile(); },
    onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ev.stopPropagation(); app.recherche.lien = armee ? null : n.id; dessinerToile(); } },
  });
  const portEntree = n.role !== "ENTREE" && h("span", { class: "port entree", "aria-hidden": "true" });
  const retrait = n.removable && h("button", { type: "button", class: "tuile-retrait", "aria-label": `${VERBES.retirer} la tuile ${n.nom}`,
    onpointerdown: (ev) => ev.stopPropagation(), onclick: (ev) => { ev.stopPropagation(); retirerTuile(n.id); } }, icone("fermer", 12, { trait: 2.4 }));
  const tuile = h("div", { class: `tuile ${n.role}` }, icone(roleIcone, 28), portEntree, portSortie, retrait);
  const bloc = h("div", { class: `tuile-bloc ${choisie ? "choisie" : ""} ${armee ? "armee" : ""}`.trim(), dataset: { tuile: n.id }, tabindex: "0", role: "button", "aria-label": `${n.nom}, ${fixe ? fixe.sous : ROLES[n.role].nom.toLowerCase()} : ouvrir`,
    style: { left: `${n.x - 33}px`, top: `${n.y}px` } },
    tuile, h("span", { class: "tuile-nom" }, n.nom), h("span", { class: "tuile-sous" }, fixe ? fixe.sous : ROLES[n.role].nom.toLowerCase()));
  bloc.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); ouvrirTuile(n.id); } });
  bloc.addEventListener("pointerdown", (ev) => {
    if (ev.target.closest(".port, .tuile-retrait")) return;
    ev.stopPropagation();
    const [px, py] = pointToile(ev);
    drag = { id: n.id, ox: px - n.x, oy: py - n.y, sx: n.x, sy: n.y, moved: false, bloc };
    bloc.setPointerCapture?.(ev.pointerId);
  });
  bloc.addEventListener("pointerup", (ev) => {
    if (ev.target.closest(".port")) return; // relâcher sur un port n'ouvre rien : c'est le geste de relier qui commence
    const d = drag;
    drag = null;
    if (d && d.moved) { sauvegarder(); dessinerToile(); return; }
    const depart = app.recherche.lien;
    if (depart && depart !== n.id) {
      const ok = n.role !== "ENTREE" && ajouterLien(depart, n.id);
      app.recherche.lien = null; app.recherche.selection = n.id; app.recherche.lienChoisi = null;
      dessinerToile();
      if (!ok) annoncer(n.role === "ENTREE" ? "« Ta saisie » n'a pas d'entrée : on ne la relie pas depuis une autre tuile." : "Ce lien existe déjà.", true);
      return;
    }
    app.recherche.selection = n.id; app.recherche.lienChoisi = null;
    dessinerToile();
    ouvrirTuile(n.id);
  });
  return bloc;
}

function deplacer(ev) {
  if (ev.buttons === 0) { drag = null; return; }
  const [px, py] = pointToile(ev);
  const nx = Math.max(10, Math.round(px - drag.ox));
  const ny = Math.max(10, Math.round(py - drag.oy));
  if (Math.abs(nx - drag.sx) > 3 || Math.abs(ny - drag.sy) > 3) drag.moved = true; // un clic n'est pas un glissement : on garde le drapeau « a bougé »
  if (!drag.moved) return;
  const n = noeud(drag.id);
  n.x = nx; n.y = ny;
  drag.bloc.style.left = `${nx - 33}px`;
  drag.bloc.style.top = `${ny}px`;
  for (const e of plan().edges) {
    if (e.from !== n.id && e.to !== n.id) continue;
    const A = noeud(e.from);
    const B = noeud(e.to);
    const d = courbe(...sortieDe(A), ...entreeDe(B));
    for (const p of zone.liens.get(e.id) || []) p.setAttribute("d", d);
  }
}

/** Pendant qu'un lien se tire : un trait pointillé du port de départ au pointeur. Sans lui on ne sait pas qu'on est en train de relier. */
function majTemp(ev) {
  const A = noeud(app.recherche.lien);
  if (!A) return;
  const [px, py] = pointToile(ev);
  zone.temp.classList.remove("cache");
  zone.temp.setAttribute("d", courbe(...sortieDe(A), px, py));
}

// ---------------------------------------------------------------- la palette

export function palette() {
  const racine = h("div", { class: "palette", role: "list", "aria-label": "Briques à poser" });
  const dessiner = () => {
    racine.replaceChildren();
    const surPlan = new Set(plan().nodes.map((n) => n.ref).filter(Boolean));
    const groupes = [{ id: "outils", nom: "Outils", entrees: app.data.outils.filter((o) => !o.retire).map((o) => ({ nom: o.nom, off: o.etat === "off", posee: false, def: () => briqueOutil(o) })) }];
    for (const c of app.data.categories) {
      groupes.push({ id: c.id, nom: c.nom, entrees: app.data.sources.filter((s) => s.cat === c.id && !s.retiree).map((s) => ({ nom: s.nom, off: s.etat === "off", posee: surPlan.has(s.id), def: () => briqueSource(s) })) });
    }
    for (const g of groupes) {
      const ouvert = app.recherche.palette === g.id;
      racine.append(h("div", { class: `palette-groupe ${ouvert ? "ouvert" : ""}`.trim(), role: "listitem" },
        h("button", { type: "button", class: "palette-groupe-tete", "aria-expanded": String(ouvert), onclick: () => { app.recherche.palette = ouvert ? null : g.id; dessiner(); } }, h("span", { class: "chev" }, icone("deplier")), g.nom, h("span", { class: "n legende" }, String(g.entrees.length))),
        ouvert && g.entrees.map((e) => {
          const muette = e.off || e.posee;
          return h("button", { type: "button", class: `palette-entree ${muette ? "muette" : ""}`.trim(), "aria-disabled": String(muette), "aria-label": `${e.nom} : ${e.off ? "éteinte" : e.posee ? "déjà posée" : "poser"}`,
            onclick: () => { if (muette) return; poserBrique(e.def()); dessiner(); } }, h("span", { class: "nom" }, e.nom), h("span", { class: "marque" }, e.off ? "éteinte" : e.posee ? "posée" : "+"));
        })));
    }
  };
  racine.redessiner = dessiner;
  dessiner();
  return racine;
}

// ---------------------------------------------------------------- la fenêtre d'une tuile

function ouIlEst(n) {
  if (n.cat) return `${app.data.categories.find((c) => c.id === n.cat)?.nom} · ${ROLES[n.role].nom.toLowerCase()}`;
  return { ENTREE: "Départ de la recherche", GRAPPES: "Résultat : les grappes", RAPPROCHER: "Brique libre · rapprocher", OUTIL: "Brique libre · outil" }[n.role] || "Brique libre";
}

export function ouvrirTuile(id) {
  if (fenetreTuile) fenetreTuile.fermer();
  const contenu = h("div", { class: "trois-col" });
  const pied = h("div", { class: "pied-boutons" });
  const couche = ouvrirCouche({ largeur: "w1040", titre: noeud(id).nom, sous: "", contenu, pied, surFermeture: () => { fenetreTuile = null; dessinerToile(); } });
  fenetreTuile = couche;
  const refresh = () => {
    const n = noeud(id);
    if (!n) { couche.fermer(); return; }
    const fixe = TUILES_FIXES[n.role];
    const a = n.ref ? (sourceParId(n.ref) || outilParId(n.ref)) : null;
    const estSource = !!(n.ref && sourceParId(n.ref));
    const io = ES_ROLE[n.role] || ES_ROLE.OUTIL;
    const recoit = a && !estSource && a.recoit ? a.recoit : io[0];
    const renvoie = a && !estSource && a.renvoie ? a.renvoie : io[1];
    const aEntree = n.role !== "ENTREE";
    const aSortie = n.role !== "GRAPPES";
    const entrants = plan().edges.filter((e) => e.to === id && noeud(e.from));
    const sortants = plan().edges.filter((e) => e.from === id && noeud(e.to));
    const aLien = (x, y) => plan().edges.some((e) => e.from === x && e.to === y);
    couche.boite.querySelector("h2").textContent = n.nom;
    const sous = couche.boite.querySelector(".fenetre-sous") || couche.boite.querySelector(".fenetre-tete > div").appendChild(h("div", { class: "fenetre-sous" }));
    sous.replaceChildren(etiquetteRole(n.role, { auto: true }), ouIlEst(n));
    const optsChamps = n.opts.map(([lib, v]) => champ({ libelle: lib, valeur: v }));
    optsChamps.forEach((c, i) => c.saisie.addEventListener("change", () => { n.opts[i][1] = c.valeur(); sauvegarder(); }));
    const estCondition = genreDe(n) === "si";
    const colLiens = (titre, liste, sens, candidats, vide) => [
      h("span", { class: "titre-champ" }, titre),
      liste.length ? h("div", { class: "liste-liens" }, liste.map((e) => {
        const autre = noeud(sens === "in" ? e.from : e.to);
        const puces = sens === "out" && estCondition && h("span", { class: "puces", role: "group", "aria-label": `Sortie vers ${autre.nom}` }, ["oui", "non"].map((mot) => puce({ libelle: mot, actif: e.label === mot, onclick: () => { etiqueterLien(e.id, e.label === mot ? null : mot); dessinerToile(); refresh(); } })));
        return h("div", { class: "lien-ligne" }, h("span", { class: "fort" }, autre.nom), puces, bouton({ libelle: `${VERBES.retirer} le lien`, icon: "retirer", variante: "danger", petit: true, onclick: () => { retirerLien(e.id); dessinerToile(); refresh(); } }));
      })) : vide && h("p", { class: "sans-lien" }, vide),
      candidats.length > 0 && h("span", { class: "legende" }, `${VERBES.ajouter} un lien ${sens === "in" ? "depuis" : "vers"} :`),
      h("div", { class: "liste-liens" }, candidats.map((c) => bouton({ libelle: c.nom, icon: "ajouter", petit: true, onclick: () => { sens === "in" ? ajouterLien(c.id, id) : ajouterLien(id, c.id); dessinerToile(); refresh(); } }))),
    ];
    contenu.replaceChildren(
      h("div", { class: "col" }, h("span", { class: "etiquette-col" }, "Entrée"),
        h("p", { class: "douce" }, recoit ? `Reçoit : ${recoit}` : "Cette tuile est le départ : rien n'entre."),
        ...(aEntree ? colLiens("Reliée à l'entrée :", entrants, "in", plan().nodes.filter((m) => m.id !== id && m.role !== "GRAPPES" && !aLien(m.id, id)), entrants.length ? null : "Aucun lien entrant : cette tuile n'est jamais interrogée. Relie-la depuis l'une de celles-ci.") : [])),
      h("div", { class: "col" }, h("span", { class: "etiquette-col" }, "La tuile"),
        h("span", { class: "fort" }, n.nom),
        a && h("p", { class: "douce" }, a.fait || a.description || ""),
        a && h("span", { class: "etat" }, h("span", { class: `pastille ${a.etat}`, "aria-hidden": "true" }), (estSource ? ETATS_SOURCE : ETATS_OUTIL)[a.etat]),
        n.ref === "ia" && h("span", { class: "marque-ia" }, icone("ia", 20), `Sortie marquée « ${MARQUE_IA} »`),
        optsChamps.length > 0 && h("div", { class: "options-grille" }, optsChamps.map((c) => c.el)),
        h("p", { class: "legende" }, (a && !estSource && a.effet ? { rien: "Effet dans le Tableau de bord : rien.", compteur: "Effet dans le Tableau de bord : un compteur.", journal: "Effet dans le Tableau de bord : le journal.", alerte: "Effet dans le Tableau de bord : une alerte." }[a.effet] : EFFET_DE_ROLE[n.role]) || "Effet dans le Tableau de bord : défini dans Réglages › Outils.")),
      h("div", { class: "col" }, h("span", { class: "etiquette-col" }, "Sortie"),
        h("p", { class: "douce" }, renvoie ? `Envoie : ${renvoie}` : "Fin du parcours : rien ne sort. Les grappes se lisent dans le Tableau de bord."),
        ...(aSortie ? colLiens("Reliée à la sortie :", sortants, "out", plan().nodes.filter((m) => m.id !== id && m.role !== "ENTREE" && !aLien(id, m.id)), sortants.length ? null : "Aucun lien sortant : son résultat se perd. Relie-la vers l'une de celles-ci.") : [])),
    );
    pied.replaceChildren(...[bouton({ libelle: VERBES.fermer, onclick: () => couche.fermer() }), n.removable && h("span", { class: "droite" }, bouton({ libelle: `${VERBES.retirer} la tuile`, icon: "retirer", variante: "danger", onclick: () => { couche.fermer(); retirerTuile(id); } }))].filter(Boolean));
  };
  refresh();
  return couche;
}

/** Utilisée par l'Aide : sélectionne une tuile sur le plan (cliquer un constat). */
export function selectionner(id) {
  if (!noeud(id)) return;
  app.recherche.selection = id; app.recherche.lien = null; app.recherche.lienChoisi = null;
  dessinerToile();
  zone?.noeuds.get(id)?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
  zone?.noeuds.get(id)?.focus?.();
}

/** Utilisée par l'Aide : pose les tuiles d'un plan proposé, sur un bouton pressé. Les tuiles déjà là ne sont pas dupliquées. */
export function poserProposition(prop) {
  const existants = new Set(plan().nodes.map((n) => n.id));
  const nouveaux = prop.nodes.filter((n) => !existants.has(n.id));
  let colonne = 0;
  for (const n of prop.nodes) {
    if (existants.has(n.id)) continue;
    const [x, y] = emplacementLibre();
    const base = { id: n.id, nom: n.nom, role: n.role, ref: n.ref, cat: n.cat, x, y, removable: n.role !== "ENTREE" && n.role !== "GRAPPES", opts: [] };
    const s = n.ref && sourceParId(n.ref);
    const o = n.ref && outilParId(n.ref);
    base.opts = s ? OPTIONS_SOURCE.map((p) => [...p]) : o ? o.options.map((p) => [...p]) : [];
    plan().nodes.push(base);
    if (base.cat && !plan().cats.includes(base.cat)) plan().cats.push(base.cat);
    colonne += 1;
  }
  for (const e of prop.edges) ajouterLien(e.from, e.to);
  sauvegarder();
  if (existants.size <= 2) ranger(); // un plan neuf est rangé en colonnes ; un plan déjà travaillé garde les tuiles là où la personne les a mises
  else dessinerToile();
  return nouveaux.length;
}
