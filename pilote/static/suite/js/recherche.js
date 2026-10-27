// Onglet Recherche : Recherche simple (07), Recherche avancée (08), Recherches sauvegardées (12).
import { api } from "./api.js";
import { h, icone } from "./dom.js";
import { agir, app, recharger } from "./etat.js";
import { PAYS, PRESETS_INFO, ROLES, VERBES, aPluriel, fmtDate, fmtNombre, SEUIL_QUOTA, AVIS_MOTEUR } from "./mots.js";
import { annoncer, avertissement, bouton, caseSource, champ, carteRepliable, groupePuces } from "./ui.js";
import { dessinerToile, initialiserPlan, palette, plan, ranger, toile, viderSauvegarde } from "./plan.js";

let delaiSimple = null;
const bascule = (cle) => () => { app.recherche.ouvert[cle] = !app.recherche.ouvert[cle]; app.rendre(); };

export function pageRecherche() {
  const s = app.data.simple;
  const nbPlan = new Set(plan().nodes.filter((n) => n.cat).map((n) => n.cat)).size;
  return h(
    "div",
    { class: "cartes" },
    carteRepliable({ titre: "Recherche simple", icon: "recherche", compte: app.data.categories.find((c) => c.id === s.preset)?.nom, ouverte: app.recherche.ouvert.simple, onbascule: bascule("simple"), corps: h("div", { class: "carte-corps" }, simple()) }),
    carteRepliable({ titre: "Recherche avancée", icon: "outil", compte: aPluriel(nbPlan, "catégorie", "catégories"), ouverte: app.recherche.ouvert.adv, onbascule: bascule("adv"), corps: h("div", { class: "carte-corps" }, avancee()) }),
    carteRepliable({ titre: "Recherches sauvegardées", icon: "reutiliser", compte: aPluriel(app.data.recherches.length, "recherche", "recherches"), ouverte: app.recherche.ouvert.sauvees, onbascule: bascule("sauvees"), corps: h("div", { class: "carte-corps" }, sauvegardees()) }),
  );
}

/** Ce qui est parti, et ce qui n'est pas parti avec sa raison : une source écartée en silence ferait croire qu'elle a répondu sans rien trouver. */
function annoncerLancement(texte, res) {
  app.recherche.bilan = (res.appliques || []).length || (res.non_appliques || []).length || (res.verifient || []).length ? res : null;
  const ecartees = res.ecartees || [];
  annoncer(`Recherche lancée : « ${texte} », sur ${aPluriel(res.lancees.length, "source", "sources")}.` + (ecartees.length ? ` Écartée${ecartees.length > 1 ? "s" : ""} : ${ecartees.map((x) => `${x.nom} (${x.raison})`).join(" ; ")}.` : "") + " Elle est dans Recherches sauvegardées.", false);
}

// ================================================================ Recherche simple

const estEteinte = (src) => src.etat === "off";
const parDefaut = (src) => !estEteinte(src) && src.role !== "VERIFIER" && !(src.cle_requise && !src.cle); // vérifier est décoché au départ ; une source dont la clé manque ne peut pas chercher : décochée aussi
const correspond = (src, pays) => pays === "Tous" || src.pays_codes.includes(pays) || src.pays_codes.includes("Mondial") || (pays === "UE" && src.pays_codes.some((c) => ["FI", "UE"].includes(c)));

function coche(src, ov, cat) {
  if (estEteinte(src)) return false; // une source éteinte dans Réglages est décochée et non cochable
  const v = ov[cat] && ov[cat][src.id];
  return v === undefined ? parDefaut(src) : v;
}

function memoriserSimple() {
  clearTimeout(delaiSimple);
  delaiSimple = setTimeout(() => api.put("/simple", app.data.simple).catch(() => {}), 400);
}

function simple() {
  const st = app.data.simple;
  const cat = st.preset;
  const [phrase, placeholder] = PRESETS_INFO[cat];
  const sources = app.data.sources.filter((x) => x.cats.includes(cat) && !x.retiree);
  const visibles = sources.filter((x) => correspond(x, st.pays));
  const ov = st.ov;
  const nbMod = sources.filter((x) => ov[cat] && ov[cat][x.id] !== undefined && ov[cat][x.id] !== parDefaut(x)).length;
  const actives = visibles.filter((x) => coche(x, ov, cat));
  const payantes = actives.filter((x) => x.cout === "payant");
  const chaudes = actives.filter((x) => x.pct !== null && x.pct >= SEUIL_QUOTA);
  const colonnes = [["CHERCHER", "CHERCHER", ["CHERCHER"]], ["VERIFIER", "VÉRIFIER", ["VERIFIER"]], ["ENRICHIR", "ENRICHIR", ["ENRICHIR"]], ["RAPPROCHER", "AUTRES", ["RAPPROCHER", "CATALOGUE", "OUTIL"]]];
  const saisie = champ({ libelle: "Ce que tu cherches", valeur: st.saisie, placeholder });
  saisie.saisie.addEventListener("input", () => { st.saisie = saisie.valeur(); memoriserSimple(); });
  const refus = h("div", { class: "cache", role: "status" });
  const maj = () => { memoriserSimple(); app.rendre(); };

  async function lancer() {
    const texte = saisie.valeur().trim();
    if (!texte) { annoncer("Dis ce que tu cherches.", true); saisie.saisie.focus(); return; }
    const detail = `${app.data.categories.find((c) => c.id === cat).nom} · pays ${st.pays}`;
    const choisies = visibles.filter((x) => coche(x, ov, cat)).map((x) => x.id);
    const res = await agir(() => api.post("/lancer", { mode: "Simple", saisie: texte, sources: choisies, cats: [cat], pays: st.pays, titre: texte.slice(0, 80), detail, simple: { preset: cat, pays: st.pays, ov, saisie: texte } }));
    if (res) { annoncerLancement(texte, res); app.recherche.ouvert.sauvees = true; app.rendre(); }
  }

  return [
    h("div", { class: "champ" }, h("span", { class: "titre-champ" }, "Préréglage"), groupePuces(app.data.categories.map((c) => [c.id, c.nom]), cat, (v) => { st.preset = v; st.pays = "Tous"; maj(); })),
    h("p", { class: "douce" }, phrase),
    h("div", { class: "champ" }, h("span", { class: "titre-champ" }, "Pays"), groupePuces(PAYS.map((p) => [p, p]), st.pays, (v) => { st.pays = v; maj(); })),
    h("div", { class: "champ" },
      h("span", { class: "titre-champ" }, "Sources"),
      h("div", { class: "simple-grille" }, colonnes.map(([cle, nom, roles]) => {
        const lignes = visibles.filter((x) => roles.includes(x.role));
        const on = lignes.filter((x) => coche(x, ov, cat)).length;
        return h("div", { class: "simple-col" },
          h("div", { class: "simple-col-tete" }, h("span", { class: `role ${cle}` }, nom === "AUTRES" ? "AUTRES" : ROLES[cle].nom), h("span", { class: "legende pale" }, lignes.length ? `${on} sur ${lignes.length}` : "—")),
          lignes.map((x) => caseSource({
            nom: x.nom, sous: roles.length > 1 ? `${ROLES[x.role].nom.toLowerCase()} · ${x.pays}` : x.pays, actif: coche(x, ov, cat), disabled: estEteinte(x), etat: estEteinte(x) ? "éteinte" : x.etat === "warn" ? "à vérifier" : null,
            onclick: () => { ov[cat] = { ...(ov[cat] || {}), [x.id]: !coche(x, ov, cat) }; maj(); },
          })));
      })),
      nbMod > 0 && h("div", {}, bouton({ libelle: VERBES.remettre, icon: "reutiliser", petit: true, onclick: () => { delete ov[cat]; maj(); } }), " ", h("span", { class: "legende" }, aPluriel(nbMod, "changement", "changements")))),
    h("div", { class: "info-ligne legende" },
      h("span", {}, `Coût : ${payantes.length ? `payant (${payantes.map((x) => x.nom).join(", ")})` : "gratuit"}`),
      h("span", {}, chaudes.length ? chaudes.map((x) => `${x.nom} : ${fmtNombre(x.quota.utilise)} / ${fmtNombre(x.quota.plafond)} ${x.quota.unite} (${x.pct} %)`).join(" · ") : "Aucun quota proche de la limite.")),
    h("div", { class: "lancer-ligne" }, saisie.el, bouton({ libelle: "Lancer la recherche", icon: "lancer", variante: "principal", onclick: lancer })),
    h("p", { class: "legende" }, AVIS_MOTEUR),
    refus,
  ];
}

// ================================================================ Recherche avancée

let paletteVue = null;
function avancee() {
  initialiserPlan();
  const p = plan();
  const saisie = champ({ libelle: "Ce que tu cherches", valeur: p.saisie || "", placeholder: "la saisie de « Ta saisie »" });
  saisie.saisie.addEventListener("input", () => { p.saisie = saisie.valeur(); app.recherche.planModifie = true; clearTimeout(app.recherche.delaiPlan); app.recherche.delaiPlan = setTimeout(() => api.put("/plan", { nodes: p.nodes, edges: p.edges, cats: p.cats, saisies: p.saisies, saisie: p.saisie }).catch(() => {}), 400); });
  paletteVue = palette();
  const zoneToile = toile();
  async function lancer() {
    const texte = saisie.valeur().trim();
    const sources = p.nodes.filter((n) => n.cat);
    if (!texte) { annoncer("Dis ce que tu cherches.", true); saisie.saisie.focus(); return; }
    if (!sources.length) { annoncer("Pose au moins une source sur le plan.", true); return; }
    await viderSauvegarde();
    const bloquants = (await api.aide("verifier_plan", { saisie: texte })).constats.filter((c) => c.niveau === "bloquant");
    if (bloquants.length) { annoncer(`Le plan a ${aPluriel(bloquants.length, "point bloquant", "points bloquants")} : ${bloquants[0].nom} ${bloquants[0].texte} Demande à l'Aide « Pourquoi ça n'a rien donné ? ».`, true); return; }
    const cats = [...new Set(sources.map((n) => n.cat))];
    const noms = cats.map((c) => app.data.categories.find((x) => x.id === c).nom);
    await api.put("/plan", { nodes: p.nodes, edges: p.edges, cats: p.cats, saisies: p.saisies, saisie: texte });
    const ids = [...new Set(sources.filter((n) => n.ref).map((n) => n.ref))];
    const res = await agir(() => api.post("/lancer", { mode: "Avancée", saisie: texte, sources: ids, cats, titre: texte.slice(0, 80), detail: noms.join(" · "), plan: { nodes: p.nodes, edges: p.edges, saisie: texte } }));
    if (res) { annoncerLancement(texte, res); app.recherche.ouvert.sauvees = true; app.rendre(); }
  }
  return [
    h("div", { class: "plan-barre" }, saisie.el,
      bouton({ libelle: VERBES.ranger, icon: "ranger", onclick: () => ranger() }),
      bouton({ libelle: "Lancer la recherche", icon: "lancer", onclick: lancer })), // secondaire : le seul bouton principal de l'écran est celui de la Recherche simple
    app.recherche.bilan && bilanVue(app.recherche.bilan),
    h("div", { class: "adv-corps" }, paletteVue, h("div", { class: "plan-zone" }, zoneToile, h("p", { class: "legende" }, AVIS_MOTEUR))),
  ];
}

/** Ce que le dernier lancement a appliqué du plan, et ce qu'il n'a pas appliqué avec la raison : ni l'un ni l'autre ne se devine. */
function bilanVue(b) {
  const liste = (xs, f) => h("ul", {}, xs.map((x) => h("li", {}, f(x))));
  return h("div", { class: "bilan", role: "status" },
    h("span", { class: "titre-champ" }, "Dernier lancement : ce que le moteur a fait du plan"),
    (b.verifient || []).length > 0 && h("span", { class: "legende" }, `Vérifient les résultats : ${b.verifient.join(", ")}.`),
    (b.appliques || []).length > 0 && [h("span", { class: "legende fort" }, "Appliqué"), liste(b.appliques, (x) => `${x.nom} — ${x.texte}`)],
    (b.non_appliques || []).length > 0 && [h("span", { class: "legende fort" }, "Pas appliqué"), liste(b.non_appliques, (x) => `${x.nom} — ${x.raison}`)]);
}

// ================================================================ Recherches sauvegardées

function sauvegardees() {
  const liste = app.data.recherches;
  if (!liste.length) return h("p", { class: "vide" }, "Aucune recherche sauvegardée. Une recherche lancée apparaît ici.");
  return h("div", {}, liste.map(ligneSauvegardee));
}

function ligneSauvegardee(r) {
  const avancee = r.mode === "Avancée";
  return h("div", { class: "sauvee", dataset: { recherche: r.id } },
    h("div", { class: "sauvee-texte" },
      h("div", { class: "sauvee-meta" }, h("span", { class: "fort" }, r.titre), h("span", { class: `mode ${avancee ? "avancee" : ""}`.trim() }, r.mode)),
      h("span", { class: "legende" }, r.detail),
      r.verification && h("span", { class: "legende", dataset: { verification: r.id } }, r.verification),
      r.emoji && h("span", { class: "legende", dataset: { emoji: r.id } }, r.emoji),
      r.ecartes && h("details", { class: "legende", dataset: { ecartes: r.id } },
        h("summary", {}, `${r.ecartes.n} écarté${r.ecartes.n > 1 ? "s" : ""} par un filtre`), // règle 1 : un retrait reste consultable
        h("ul", {}, r.ecartes.noms.map((nom) => h("li", {}, nom))),
        r.ecartes.noms.length < r.ecartes.n && h("span", { class: "legende" }, `Les ${r.ecartes.noms.length} premiers sont listés.`))),
    h("span", { class: "legende chiffres" }, fmtDate(r.date)),
    h("span", { class: "legende fort" }, r.resultat),
    h("div", { class: "sauvee-actions" },
      bouton({ libelle: VERBES.reutiliser, icon: "reutiliser", petit: true, onclick: () => reutiliser(r), "aria-label": `${VERBES.reutiliser} ${r.titre}` }),
      bouton({ libelle: VERBES.supprimer, icon: "supprimer", variante: "danger", petit: true, onclick: () => confirmerSuppression(r), "aria-label": `${VERBES.supprimer} ${r.titre}` })));
}

/** RÉUTILISER : recharge la recherche dans l'écran dont elle vient. Une recherche avancée restitue les tuiles à leurs coordonnées et TOUS les liens. */
async function reutiliser(r) {
  if (r.mode === "Avancée") {
    const p = r.plan;
    const ok = await agir(() => api.put("/plan", { nodes: p.nodes, edges: p.edges, cats: p.cats || [], saisies: p.saisies || {}, saisie: p.saisie || "" }), { rechargerApres: true });
    if (!ok) return;
    app.recherche.ouvert.adv = true; app.recherche.selection = null; app.recherche.lien = null; app.recherche.lienChoisi = null;
    app.rendre();
    annoncer(`« ${r.titre} » est rechargée dans la Recherche avancée, avec ses tuiles et ses liens.`);
  } else {
    const s = r.simple || {};
    await agir(() => api.put("/simple", { preset: s.preset || r.cats[0], pays: s.pays || "Tous", ov: s.ov || {}, saisie: s.saisie || "" }), { succes: `« ${r.titre} » est rechargée dans la Recherche simple.` });
    app.recherche.ouvert.simple = true;
    app.rendre();
  }
}

/** SUPPRIMER est définitif : fenêtre d'avertissement obligatoire, et le serveur exige la confirmation. */
function confirmerSuppression(r) {
  avertissement({
    titre: `${VERBES.supprimer} « ${r.titre} » ?`,
    points: [
      "Cette recherche est effacée pour de bon de la liste.",
      ...(r.mode === "Avancée" ? ["Son plan de travail, avec ses tuiles et ses liens, est effacé avec elle."] : []),
      "Les grappes déjà trouvées par cette recherche ne sont pas effacées.",
      "Cette action ne se défait pas.",
    ],
    verbe: VERBES.supprimer,
    danger: true,
    onconfirmer: () => agir(() => api.supprimer(`/recherches/${r.id}?confirme=true`), { succes: `« ${r.titre} » est supprimée.` }),
  });
}

export { dessinerToile, recharger };
