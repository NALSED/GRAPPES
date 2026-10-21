// Test de fumée de static/lancement.js sous Node : rend la page avec des réponses d'API fabriquées et vérifie le HTML.
import fs from "node:fs";
import vm from "node:vm";
const els = {};
const mk = (id) => ({ id, innerHTML: "", textContent: "", value: "", style: {}, disabled: false, checked: true, dataset: {}, children: [],
  querySelector: () => mk("sous-" + id), querySelectorAll: () => [], appendChild() {}, insertBefore() {}, remove() {}, addEventListener() {} });
const el = (id) => (els[id] ??= mk(id));
const doc = { getElementById: el, querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, dispatchEvent() {},
  createElement: () => mk("nouveau"), createTextNode: () => ({}) };
const encours = { id: "r1", etat: "en_cours", sujet: { quoi: "clubs de handball" }, message: "", noms: 0, tries: 0,
  avancement: { etape: "verification", appels_faits: 7, appels_prevus: 18, noms: 41, secondes: 70,
    prises: { Tavily: { prevus: 3, faits: 3, trouves: 30, fini: true }, Wikipedia: { prevus: 3, faits: 1, trouves: 0, fini: false } } } };
const reponses = {
  "/api/lancement/options": { profondeurs: [{ id: "strict", nom: "Strict", description: "requête exacte", appels: 5 }, { id: "normal", nom: "Normal", description: "reformulations", appels: 18 }], profondeur_par_defaut: "normal", limites_par_defaut: { temps_minutes: 30 } },
  "/api/programmes": [{ id: "p1", libelle: "clubs — tous les jours 10 h 00", actif: true, prochaine: "2026-10-14T06:00:00Z" }, { id: "p2", libelle: "librairies — lundi 08 h 00", actif: false, prochaine: null }],
  "/api/recherches": [encours, { id: "r0", etat: "terminee", sujet: { quoi: "festivals" }, noms: 1204, tries: 0, avancement: {} }],
  "/api/recherches/r1": encours,
};
const ctx = { document: doc, console, location: { origin: "https://x" }, localStorage: { getItem: (k) => (k === "g_recherche" ? "r1" : null), setItem() {} },
  CustomEvent: class {}, setInterval: () => 0, clearInterval() {}, fetch: async (u) => ({ ok: u in reponses, status: 404, json: async () => reponses[u] }) };
vm.createContext(ctx);
for (const f of ["static/commun.js", "static/lancement.js"]) vm.runInContext(fs.readFileSync(f, "utf8"), ctx);
await new Promise((r) => setTimeout(r, 80));
const n = (s, re) => (s.match(re) || []).length;
const g = els.gauges.innerHTML;
const ok = [
  ["profondeur : deux crans, coût exact", n(els.depth.innerHTML, /<button/g) === 2 && els.depth.innerHTML.includes("jusqu'à 5 appels")],
  ["cran par défaut sélectionné", /class="on" data-id="normal"/.test(els.depth.innerHTML)],
  ["compte d'appels exact", els.rcalls.textContent === "7 / 18 appels"],
  ["noms collectés", els.rn.textContent === 41],
  ["temps en fourchette au-delà d'une minute", /^entre \d+ et \d+ min$/.test(els.reta.textContent)],
  ["jauges aux trois couleurs du flux", g.includes("g s1") && g.includes("g s2") && g.includes("g s3")],
  ["jauge de prise terminée à 100 %", g.includes("width:100%")],
  ["aucun résultat (nom) sur cette page", !/Montpellier|Fenix/.test(Object.values(els).map((e) => e.innerHTML).join(""))],
  ["programmées : une active, une suspendue", n(els.programmees.innerHTML, /checked/g) === 1 && els.programmees.innerHTML.includes("suspendue")],
  ["dernières recherches : compte des noms et des triés", els.dernieres.innerHTML.includes("0 trié") && /1.204/.test(els.dernieres.innerHTML.replace(/\s| /g, "."))],
  ["bouton d'arrêt visible pendant la course", els.stop.style.display === "inline-block"],
];
for (const [nom, b] of ok) console.log((b ? "ok   " : "ÉCHEC ") + nom);
process.exit(ok.every(([, b]) => b) ? 0 : 1);
