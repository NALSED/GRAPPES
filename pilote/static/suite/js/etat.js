// L'état partagé de la page : les données du serveur, et ce que la personne est en train de regarder (rien de tout cela n'est une donnée de grappes).
import { api, Refus } from "./api.js";
import { annoncer } from "./ui.js";

export const app = {
  data: null, // la réponse de /api/suite/etat
  onglet: "recherche",
  reglages: { sous: "sources", ouverte: "entreprises", filtre: "" },
  tri: { donnees: null, ouvert: false },
  recherche: { ouvert: { simple: true, adv: true, sauvees: true }, palette: "outils", message: "", selection: null, lien: null, lienChoisi: null },
  rendre: () => {},
};

export async function recharger() {
  app.data = await api.etat();
  if (app.onglet === "tri") app.tri.donnees = await api.tri();
  app.rendre();
}

/** Exécute une action du serveur : en cas de refus, la phrase en français est montrée telle quelle, et rien ne change à l'écran. */
export async function agir(fn, { succes, rechargerApres = true } = {}) {
  try {
    const res = await fn();
    if (rechargerApres) await recharger();
    if (succes) annoncer(succes);
    return res;
  } catch (e) {
    annoncer(e instanceof Refus ? e.message : "Quelque chose a échoué.", true);
    return null;
  }
}

export const sourcesDe = (cat) => app.data.sources.filter((s) => s.cat === cat);
export const sourceParId = (id) => app.data.sources.find((s) => s.id === id);
export const outilParId = (id) => app.data.outils.find((o) => o.id === id);
