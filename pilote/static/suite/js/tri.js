// Onglet Tri (spécification 16) : la file des rapprochements que Splink propose et qu'une PERSONNE tranche.
// La confiance est calculée par le serveur, jamais saisie ; l'état de chaque ligne (accord, désaccord, absence) aussi : ici on ne fait que le dessiner.
import { api } from "./api.js";
import { h, icone } from "./dom.js";
import { agir, app } from "./etat.js";
import { TRI, VERBES, aPluriel, compteRapprochements, fmtDate } from "./mots.js";
import { bouton, carteRepliable } from "./ui.js";

const NIVEAU = { haute: 85, moyenne: 60 }; // à partir de 85 % : etat-ok ; à partir de 60 % : etat-attention ; en dessous : neutre (le rouge est réservé à retirer et supprimer)
const LIBELLES = { nom: "Nom", ville: "Ville", numero: "Identifiant" };

function explication(pourquoi) {
  return Object.entries(pourquoi || {}).map(([champ, v]) => `${LIBELLES[champ] || champ} : ${v.niveau}${v.niveau === "absent d'un côté" ? "" : ` (×${Number((2 ** v.poids).toPrecision(2))})`}`).join(" · ");
}

function ficheColonne(f) {
  return h("div", { class: "rapp-fiche" },
    h("div", { class: "rapp-source" }, h("span", { class: "fort" }, f.source), h("span", { class: "fiab", title: "Fiabilité de la source (A à F)" }, f.fiabilite)),
    f.lignes.map((l) => h("div", { class: "rapp-ligne" }, h("span", { class: "legende pale" }, l.libelle), h("span", { class: `rapp-valeur ${l.etat}` }, l.valeur || TRI.absent))));
}

function carte(c) {
  const classe = c.confiance >= NIVEAU.haute ? "haute" : c.confiance >= NIVEAU.moyenne ? "moyenne" : "basse";
  const bilan = explication(c.pourquoi);
  return h("article", { class: "rapp-carte", dataset: { rapprochement: String(c.id) } },
    h("div", { class: "rapp-tete" },
      icone("rapprocher"), h("h2", { class: "rapp-titre" }, c.titre),
      h("span", { class: `rapp-confiance ${classe}`, title: bilan, "aria-label": `Confiance ${c.confiance} %. ${bilan}` },
        h("span", { class: "jauge", "aria-hidden": "true" }, h("span", { style: { width: `${c.confiance}%` } })), h("span", { class: "chiffres fort" }, `${c.confiance} %`))),
    h("div", { class: "rapp-fiches" }, c.fiches.map(ficheColonne)),
    h("div", { class: "pied-boutons" },
      bouton({ libelle: VERBES.confirmer, variante: "principal", onclick: () => trancher(c, "confirmer") }),
      bouton({ libelle: VERBES.separer, onclick: () => trancher(c, "separer") })));
}

async function trancher(c, verbe) {
  await agir(() => api.post(`/tri/${c.id}/${verbe}`, {}), { succes: verbe === "confirmer" ? "Rapprochement confirmé : les deux fiches se rejoignent dans la grappe. Rien n'est effacé." : "Rapprochement séparé : les deux fiches restent distinctes. Rien n'est effacé." });
}

function ligneTranchee(c) {
  const confirme = c.etat === "confirme";
  return h("div", { class: "sauvee", dataset: { rapprochement: String(c.id) } },
    h("div", { class: "sauvee-texte" }, h("span", { class: "fort" }, c.titre), h("span", { class: "legende" }, c.fiches.map((f) => f.lignes[0].valeur).join(" · "))),
    h("span", { class: "legende chiffres" }, c.decide_le ? fmtDate(c.decide_le) : ""),
    h("span", { class: `mode ${confirme ? "" : "avancee"}`.trim() }, confirme ? TRI.confirme : TRI.separe),
    // les deux gestes se refont : sur une décision, le bouton propose l'autre
    bouton({ libelle: confirme ? VERBES.separer : VERBES.confirmer, petit: true, onclick: () => trancher(c, confirme ? "separer" : "confirmer") }));
}

export function pageTri() {
  const d = app.tri.donnees;
  if (!d) return h("p", { class: "vide" }, "Chargement…");
  return [
    h("div", { class: "page-tete" }, h("div", { class: "page-titre" }, h("h1", {}, "Tri"), h("p", { class: "douce" }, d.a_examiner.length ? compteRapprochements(d.a_examiner.length) : ""))),
    d.a_examiner.length ? h("div", { class: "cartes" }, d.a_examiner.map(carte)) : h("p", { class: "note" }, TRI.vide),
    carteRepliable({ titre: TRI.tranches, compte: aPluriel(d.tranches.length, "décision", "décisions"), ouverte: app.tri.ouvert, onbascule: () => { app.tri.ouvert = !app.tri.ouvert; app.rendre(); },
      corps: h("div", { class: "carte-corps" }, d.tranches.length ? d.tranches.map(ligneTranchee) : h("p", { class: "vide" }, "Aucune décision pour l'instant.")) }),
  ];
}
