// Assistant (fiche 02) sous Node : première installation, étapes dans l'ordre, menu caché, récapitulatif, réouverture d'une étape.
// Usage : node tests/js/rendu_assistant.mjs <reglages-premiere.json> <reglages-existante.json>
import fs from "node:fs";
import { creer } from "./faux_dom.mjs";
const premiere = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const existante = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const bilan = [], ok = (n, b) => bilan.push([n, b]);
const lanceur = (D) => {
  const d = creer({ reponses: {
    "/api/reglages": D,
    "POST /api/sources/tavily/tester": { statut: "echec", raison: "La clé d'API (TAVILY_API_KEY) est absente : ajoutez-la avant d'activer cette source.", etat_phrase: "Test échoué le 13/10/2026 à 10:00 : clé absente." },
    "POST /api/sources/wikipedia/tester": { statut: "ok", raison: "", etat_phrase: "Vérifiée hors ligne le 13/10/2026 à 10:00." },
    "POST /api/assistant/terminer": { ok: true }, "POST /api/assistant/etape/2": { ok: true }, "POST /api/presets/personnaliser": { id: "ma-copie", nom: "Ma copie", sources: [] },
  }, prompt: () => "Ma copie" });
  const rouvrir = [1, 2, 3].map(() => ({ dataset: {}, set onclick(f) { this._f = f; }, get onclick() { return this._f; } }));
  rouvrir.forEach((b, i) => (b.dataset.rouvrir = String(i + 1)));
  d.declarer("button[data-rouvrir]", rouvrir);
  d.charge("static/commun.js", "static/assistant.js");
  return { d, rouvrir };
};

// ---------- A. première installation ----------
{
  const { d } = lanceur(premiere);
  await d.attendre(120);
  const aff = (id) => d.el(id).style.display;
  ok("première installation : l'assistant s'affiche", aff("assistant") === "block");
  ok("le menu principal est caché pendant l'assistant", d.doc.body.classList.contains("sans-menu"));
  ok("étape 1 seule visible, pas de « précédent »", aff("as-e1") === "block" && aff("as-e2") === "none" && aff("as-e3") === "none" && aff("as-e4") === "none" && aff("as-prec") === "none");
  const phrase1 = fs.readFileSync("static/index.html", "utf8");
  ok("les trois phrases de la fiche sont affichées", phrase1.includes("Choisis où le programme va chercher. Chaque preset est un lot de sources prêtes à l'emploi pour un type de recherche.")
    && phrase1.includes("Le programme recoupe chaque nom trouvé avec d'autres sources pour te dire s'il est confirmé. Tu peux la désactiver si tu préfères le brut.")
    && phrase1.includes("Choisis ce que tu récupères à la fin : format et emplacement."));
  const cartes = d.el("as-presets").querySelectorAll("input[data-preset]");
  ok("une carte par preset (huit au moins) avec un bouton « Personnaliser »", cartes.length >= 8 && d.el("as-presets").innerHTML.split("Personnaliser à partir de ce preset").length - 1 === cartes.length);
  ok("chaque carte dit son coût et ses sources", /Coût : (gratuit|payant)/.test(d.el("as-presets").innerHTML));
  const web = cartes.find((c) => c.dataset.preset === "web");
  web.checked = true; web.onchange(); await d.attendre();
  const srcWeb = d.el("as-presets").querySelectorAll("input[data-src]").filter((i) => i.checked).map((i) => i.dataset.src);
  ok("cocher un preset coche ses sources allumées par défaut", srcWeb.includes("tavily"));
  ok("le champ de clé apparaît pour une source à clé", d.el("as-cles").innerHTML.includes('data-cle-champ="TAVILY_API_KEY"') && d.el("as-cles").innerHTML.includes("absente"));
  ok("le plafond est demandé dès qu'une source payante est cochée", d.el("as-plafond-w").style.display === "block");
  await d.el("as-suiv").onclick(); await d.attendre();
  ok("étape 2 ensuite (violet)", aff("as-e2") === "block" && aff("as-e1") === "none");
  await d.el("as-suiv").onclick(); await d.attendre();
  ok("étape 3 ensuite (ambre)", aff("as-e3") === "block" && aff("as-e2") === "none");
  ok("les formats sont proposés", d.el("as-formats").querySelectorAll("input[data-fmt]").length >= 7);
  await d.el("as-suiv").onclick(); await d.attendre();
  ok("dernier écran : un récapitulatif avec un bouton Tester par source", aff("as-e4") === "block" && d.el("as-recap").querySelectorAll("button[data-tester]").length >= 1);
  ok("le récapitulatif affiche l'état de chaque source", /Pas encore testée|Vérifiée|Test échoué/.test(d.el("as-recap").innerHTML));
  ok("le bouton final entre dans le menu", /Terminer et entrer dans le menu/.test(d.el("as-suiv").textContent));
  const t = d.el("as-recap").querySelectorAll("button[data-tester]").find((b) => b.dataset.tester === "tavily");
  await t.onclick(); await d.attendre();
  ok("Tester affiche le résultat (ici : clé absente)", d.el("as-etat-tavily").textContent.includes("clé absente") || d.el("as-etat-tavily").textContent.includes("absente"));
  await d.el("as-suiv").onclick(); await d.attendre();
  const fin = d.appels.find((a) => a.cle === "POST /api/assistant/terminer");
  ok("terminer envoie les trois étapes d'un coup", !!fin && "etape1" in fin.corps && "etape2" in fin.corps && "etape3" in fin.corps && fin.corps.etape1.chercher.includes("tavily"));
  ok("terminer recharge la page (le menu s'ouvre)", d.ctx.__recharge === true);
}

// ---------- B. configuration déjà présente : l'assistant est sauté ----------
{
  const { d } = lanceur(existante);
  await d.attendre(120);
  ok("configuration existante : l'assistant est sauté", d.el("assistant").style.display !== "block" && !d.doc.body.classList.contains("sans-menu"));
}

// ---------- C. rouvrir l'étape 2 depuis Réglages ----------
{
  const { d, rouvrir } = lanceur(existante);
  await d.attendre(120);
  await rouvrir[1].onclick(); await d.attendre();
  ok("réouverture : directement à l'étape 2", d.el("assistant").style.display === "block" && d.el("as-e2").style.display === "block" && d.el("as-e1").style.display === "none" && d.el("as-e3").style.display === "none");
  ok("réouverture : une seule étape proposée, pas de « précédent »", d.el("as-etapes").innerHTML.split("as-chip").length - 1 === 1 && d.el("as-prec").style.display === "none");
  ok("réouverture : le menu reste accessible", !d.doc.body.classList.contains("sans-menu"));
  await d.el("as-suiv").onclick(); await d.attendre();
  const e = d.appels.find((a) => a.cle === "POST /api/assistant/etape/2");
  ok("réouverture : seule l'étape 2 est envoyée", !!e && "verifier" in e.corps.donnees && !("pays" in e.corps.donnees) && !d.appels.some((a) => a.cle.includes("/etape/1") || a.cle.includes("/etape/3") || a.cle.includes("terminer")));
}
for (const [nom, b] of bilan) console.log((b ? "ok   " : "ÉCHEC ") + nom);
process.exit(bilan.every(([, b]) => b) ? 0 : 1);
