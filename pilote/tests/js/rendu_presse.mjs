// Test de fumée de static/presse.js sous Node : la liste des flux RSS (Réglages) et l'encadré Contexte (Lancement).
import fs from "node:fs";
import vm from "node:vm";
const els = {};
const mk = (id) => ({ id, innerHTML: "", textContent: "", value: "", style: {}, disabled: false, checked: false, dataset: {}, files: null,
  querySelector: () => null, querySelectorAll: () => [], appendChild() {}, addEventListener() {} });
const el = (id) => (els[id] ??= mk(id));
const doc = { getElementById: el, querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, dispatchEvent() {}, createElement: () => mk("n") };
const appels = [];
const reponses = {
  "/api/flux-rss": { flux: [{ id: "rss-journal-1", nom: "Journal <Exemple>", url: "https://journal.example/rss.xml", pays: "FR", format: "rss" }] },
  "/api/recherches/r1/contexte": { articles: [
    { titre: "Club Imaginaire : victoire", source: "Journal Exemple", date: "2026-10-12", url: "https://journal.example/a" },
    { titre: "Piège <script>alert(1)</script>", source: "Autre", date: "", url: "javascript:alert(1)" }], nombre: 2, note: "Titres des articles déjà collectés. Aucune nouvelle collecte n'est faite pour les afficher." },
};
const window = {};
const ctx = { document: doc, window, console, location: { origin: "https://x" }, localStorage: { getItem: () => null, setItem() {} }, CustomEvent: class {},
  fetch: async (u, o) => { appels.push(u); return { ok: u in reponses, status: 404, json: async () => reponses[u] }; } };
vm.createContext(ctx);
for (const f of ["static/commun.js", "static/presse.js"]) vm.runInContext(fs.readFileSync(f, "utf8"), ctx);
await new Promise((r) => setTimeout(r, 50));
const flux = els["flux-rss"].innerHTML;
window.chargerContexte("r1", "fin");
window.chargerContexte("r1", "fin");  // la même recherche, au même état : pas de second chargement
await new Promise((r) => setTimeout(r, 50));
const c = els.contexte.innerHTML;
const ok = [
  ["le flux est listé avec son nom échappé", flux.includes("Journal &lt;Exemple&gt;") && !flux.includes("<Exemple>")],
  ["bouton pour retirer un flux", flux.includes('data-suppr="rss-journal-1"')],
  ["ajout à la main et import OPML proposés", flux.includes('id="flux-ajout"') && flux.includes('id="flux-opml"')],
  ["le Contexte liste les titres avec journal et date", c.includes("Club Imaginaire : victoire") && c.includes("Journal Exemple") && c.includes("2026-10-12")],
  ["le Contexte dit qu'aucune collecte n'est faite", c.includes("Aucune nouvelle collecte")],
  ["un titre piégé est échappé, un lien javascript: n'est pas cliquable", c.includes("&lt;script&gt;") && !c.includes("<script>") && !c.includes("javascript:")],
  ["le Contexte n'est chargé qu'une fois", appels.filter((u) => u.endsWith("/contexte")).length === 1],
];
for (const [nom, b] of ok) console.log((b ? "ok   " : "ÉCHEC ") + nom);
process.exit(ok.every(([, b]) => b) ? 0 : 1);
