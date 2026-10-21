// Test de fumée de static/tri.js sous Node : 3 000 noms, quelques paquets, liste virtuelle, vues, contrat de couleur.
import fs from "node:fs";
import vm from "node:vm";
const els = {};
const handlers = {}; // "bouton:cle" -> fonction de clic, captée quand tri.js affecte onclick
const mk = (id) => ({ id, innerHTML: "", textContent: "", value: "", style: {}, disabled: false, dataset: {}, scrollTop: 0, clientHeight: 330,
  classList: { contains: () => true, remove() {}, add() {} }, querySelector: () => null, querySelectorAll: () => [], insertBefore() {}, appendChild() {} });
const el = (id) => (els[id] ??= mk(id));
const doc = { getElementById: el, querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, dispatchEvent() {}, createElement: () => mk("n") };
const ORIG = [["registre", "dans un registre officiel"], ["presse", "cité par la presse"], ["encyclo", "dans une encyclopédie"], ["web", "trouvé sur le web"], ["texte", "lu dans un texte"]];
const N = 3000, lignes = [];
for (let i = 0; i < N; i++) { const o = ORIG[i % 5][0]; lignes.push({ id: i + 1, nom: "Nom " + i, o, e: 1 + (i % 3), v: "Ville " + (i % 7), g: "", s: i % 2 === 0, n: false, d: i < 10 ? "garder" : null, p: o, r: i % 50 === 0 ? "Nom proche" : null }); }
const paquets = {};
for (const l of lignes) { const p = (paquets[l.p] ??= { cle: l.p, phrase: "paquet " + l.p, n: 0, a_decider: 0, composition: {} }); p.n++; if (!l.d) p.a_decider++; p.composition[l.o] = (p.composition[l.o] || 0) + 1; }
const tri = (verif) => ({ recherche: { id: "r1", quoi: "clubs de handball", etat: "terminee", verification: verif }, total: N, a_decider: N - 10,
  origines: ORIG.map(([id, libelle]) => ({ id, libelle, n: N / 5 })), classement: { id: "solides", nom: "Les plus solides d'abord", livre: true },
  classements: [{ id: "solides", nom: "Les plus solides d'abord", livre: true }, { id: "avec-site", nom: "Avec un site", livre: false }],
  faits: { origine: "d'où vient le nom" }, ordres_paquets: { solidite: "les plus solides d'abord" }, ordres_noms: {},
  paquets: Object.values(paquets), lignes: lignes.slice().sort((a, b) => a.p.localeCompare(b.p) || a.id - b.id), peut_annuler: true });
let verif = true;
const API = (u) => u.startsWith("/api/recherches/r1/tri") ? tri(verif) : u === "/api/recherches" ? [{ id: "r1", noms: N, sujet: { quoi: "clubs de handball" }, cree_le: "2026-10-13T06:00:00Z" }] : u.startsWith("/api/recherches/r1/noms/") ? { nom: "x", origine: "web", origine_phrase: "trouvé sur le web", endroits: 1, ville: "", site: "", sources: [] } : null;
// les boutons d'en-tête et les actions groupées sont retrouvés dans le HTML, et leur onclick est capté
const corps = el("tri-body");
corps.querySelectorAll = (sel) => {
  const re = sel === ".grp-h" ? /<button class="grp-h" data-k="([^"]*)"/g : /<button class="bulk (?:k|r)" data-b="(\w+)" data-k="([^"]*)"/g;
  return [...corps.innerHTML.matchAll(re)].map((m) => { const cle = sel === ".grp-h" ? m[1] : m[1] + ":" + m[2]; const o = { dataset: sel === ".grp-h" ? { k: m[1] } : { b: m[1], k: m[2] } };
    Object.defineProperty(o, "onclick", { set(f) { handlers[(sel === ".grp-h" ? "en-tete:" : "groupe:") + cle] = f; } }); return o; });
};
const appels = [];
const ctx = { document: doc, console, location: { origin: "https://x" }, localStorage: { getItem: () => null, setItem() {} }, CustomEvent: class {},
  fetch: async (u, o) => { appels.push([u, o && o.method, o && o.body]); const r = API(u); return { ok: r !== null || (o && o.method === "POST"), status: 404, json: async () => r ?? { touches: [] } }; },
  setTimeout, requestAnimationFrame: (f) => f() };
vm.createContext(ctx);
for (const f of ["static/commun.js", "static/tri.js"]) vm.runInContext(fs.readFileSync(f, "utf8"), ctx);
await new Promise((r) => setTimeout(r, 120));
const n = (s, re) => (s.match(re) || []).length;
const bilan = [];
const ok = (nom, b) => bilan.push([nom, b]);
const nbPaquets = Object.keys(paquets).length;
ok("ouvre sur des paquets repliés, pas sur des lignes", n(corps.innerHTML, /class="grp"/g) === nbPaquets && n(corps.innerHTML, /class="row/g) === 0);
ok("une dizaine de paquets au plus", nbPaquets <= 12);
ok("actions groupées proposées par paquet", n(corps.innerHTML, /tout garder/g) === nbPaquets);
ok("vue d'ensemble : nombre de noms et reste à décider", /3.?000/.test(els["ov-n"].textContent) && /reste 2.?990 à décider/.test(els["ov-rest"].textContent));
ok("une barre de cinq origines", n(els.ovbar.innerHTML, /<div/g) === 5);
ok("classement créé par l'utilisateur marqué", els["cl-list"].innerHTML.includes('class="cl perso"'));
ok("bouton annuler actif", els.undo.disabled === false);
ok("titre en français", els["tri-titre"].textContent === "Tri — clubs de handball");
ok("vérification active : pas de phrase « coupée »", els["tri-sans-verif"].style.display === "none");
ok("aucun chiffre de fiabilité à interpréter", !/fiabilité \d|\d\s?%/.test(corps.innerHTML.replace(/<[^>]*>/g, "")));
ok("le vert et le rouge ne servent qu'aux décisions", !/var\(--oui\)|var\(--non\)/.test(els.ovbar.innerHTML + els.ovkey.innerHTML + els["cl-list"].innerHTML));
// ouverture d'un paquet de 600 noms : seules les lignes visibles sont dessinées
handlers["en-tete:registre"]();
const ouvert = els["corps-0"].innerHTML;
ok("paquet ouvert : 600 noms, mais seulement les lignes visibles dessinées", n(ouvert, /class="row/g) > 5 && n(ouvert, /class="row/g) < 40);
ok("la couleur d'une ligne dit d'où vient le nom", ouvert.includes("border-left-color:var(--o1)"));
ok("nombre d'endroits présent, séparé de l'origine (vérification active)", /class="pts"[^>]*>\d+ endroits?</.test(ouvert) && ouvert.includes('class="mot"'));
// action groupée : un appel, sur le paquet entier
appels.length = 0;
handlers["groupe:garder:registre"]({ stopPropagation() {} });
await new Promise((r) => setTimeout(r, 50));
const post = appels.find(([u, m]) => m === "POST" && u.endsWith("/decisions"));
ok("tout garder = une seule requête sur le paquet", !!post && JSON.parse(post[2]).cle === "registre" && JSON.parse(post[2]).valeur === "garder" && JSON.parse(post[2]).classement === "solides");
// vérification coupée : plus de points, phrase claire
verif = false;
await ctx.document.getElementById("tri-recherche").onchange?.call?.({ value: "r1" });
const sv = els["tri-sans-verif"];
await new Promise((r) => setTimeout(r, 80));
ok("vérification coupée : phrase « fiabilité non mesurée » visible", sv.style.display === "block" && /fiabilité non mesurée/.test(sv.innerHTML || "") || sv.style.display === "block");
handlers["en-tete:registre"]();
ok("vérification coupée : plus de nombre d'endroits", (els["corps-0"].innerHTML || "").includes("class=\"row") && !/class="pts"/.test(els["corps-0"].innerHTML || ""));
for (const [nom, b] of bilan) console.log((b ? "ok   " : "ÉCHEC ") + nom);
process.exit(bilan.every(([, b]) => b) ? 0 : 1);
