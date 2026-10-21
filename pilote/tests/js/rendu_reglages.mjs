// Test de fumée de static/reglages.js sous Node : rend la page avec une réponse d'API réelle et vérifie le HTML produit.
// Usage : node tests/js/rendu_reglages.mjs <fichier-json-de-/api/reglages>
import fs from "node:fs";
import vm from "node:vm";
const donnees = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const els = {};
const el = (id) => (els[id] ??= { id, innerHTML: "", textContent: "", value: "", style: {}, checked: true, querySelectorAll: () => [], querySelector: () => null, dataset: {} });
const doc = { getElementById: el, querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, dispatchEvent() {} };
const ctx = { document: doc, console, location: { origin: "https://x" }, localStorage: { getItem: () => null, setItem() {} }, window: { prompt: () => null },
  CustomEvent: class {}, fetch: async () => ({ ok: true, json: async () => donnees }) };
vm.createContext(ctx);
for (const f of ["static/commun.js", "static/reglages.js"]) vm.runInContext(fs.readFileSync(f, "utf8"), ctx);
await new Promise((r) => setTimeout(r, 50));
const n = (s, re) => (s.match(re) || []).length;
const tout = el("list1").innerHTML + el("list2").innerHTML + el("list3").innerHTML + el("presets").innerHTML;
const ok = [
  ["une ligne par source en ①", n(el("list1").innerHTML, /class="srow"/g) === donnees.parties.recherche.length],
  ["des familles : toutes, y compris les vides en gris", n(el("fam1").innerHTML, /<button/g) === donnees.familles.length + 1 && el("fam1").innerHTML.includes("vide")],
  ["case « chercher » en ① et « vérifier » en ②", el("list1").innerHTML.includes('data-p="1"') && el("list2").innerHTML.includes('data-p="2"')],
  ["la main (première / seconde) est dite", /première main|seconde main/.test(el("list1").innerHTML)],
  ["l'état connu est écrit avec sa phrase (dans les détails)", /Pas encore testée|Vérifiée hors ligne|Test échoué/.test(el("list1").innerHTML)],
  ["la ligne ne garde que le nom et gratuite / payante", /class="prix">(gratuite|payante)</.test(el("list1").innerHTML) && n(el("list1").innerHTML, /class="prix"/g) === donnees.parties.recherche.length],
  ["un voyant par ligne, vert pour une source disponible", n(el("list1").innerHTML, /class="dot (ok|warn|err|off)"/g) === donnees.parties.recherche.length && /class="dot ok"/.test(el("list1").innerHTML)],
  ["un bouton pour retirer chaque source", n(el("list1").innerHTML, /data-retirer=/g) === donnees.parties.recherche.length && n(el("list2").innerHTML, /data-retirer=/g) === donnees.parties.verification.length],
  ["les blocs repliés disent leur état et un rappel", el("e1").textContent.includes("active") && el("c1").textContent.length > 0 && el("e2").textContent.length > 0 && el("r-budget").textContent.includes("plafond") && el("r-bases").textContent.includes("pays")],
  ["la clé est dite présente ou absente, jamais montrée", /Clé d’API : <b>(présente|absente)<\/b>/.test(el("list1").innerHTML)],
  ["huit cartes de preset", n(el("presets").innerHTML, /data-preset=/g) === 8 && n(el("presets").innerHTML, /Personnaliser à partir de ce preset/g) === 8],
  ["le plafond est affiché", el("budget-plafond").value === donnees.budget.plafond_mensuel_usd],
  ["compte des actives", /^\d+ active/.test(el("e1").textContent) && /\d+ prête/.test(el("c1").textContent)],
  ["les couleurs viennent des classes du voyant, pas de styles écrits dans la page", !/var\(--(oui|non|attn)/.test(tout)],
  ["aucune valeur de clé dans la page", !/(sk-|SENTINELLE|api[_-]?key["']?\s*[:=]\s*["'][A-Za-z0-9]{12})/i.test(tout)],
];
for (const [nom, b] of ok) console.log((b ? "ok   " : "ÉCHEC ") + nom);
process.exit(ok.every(([, b]) => b) ? 0 : 1);
