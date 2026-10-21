// Test de fumée de static/ajout.js sous Node : appeler une fois, désigner les champs en cliquant, tester, enregistrer.
import fs from "node:fs";
import vm from "node:vm";
const els = {};
const clics = {}; // "pick:champ" / "cat:id" -> fonction
const mk = (id) => ({ id, innerHTML: "", textContent: "", value: "", style: {}, disabled: false, dataset: {}, classList: { toggle() {}, contains: () => true, remove() {}, add() {} },
  querySelector: () => null, querySelectorAll: () => [], addEventListener() {} });
const el = (id) => (els[id] ??= mk(id));
const doc = { getElementById: el, querySelectorAll: () => [], querySelector: () => null, addEventListener() {}, dispatchEvent() {}, createElement: () => mk("n") };
el("raw").querySelectorAll = () => [...el("raw").innerHTML.matchAll(/data-f="([^"]*)"/g)].map((m) => { const o = { dataset: { f: m[1] } }; Object.defineProperty(o, "onclick", { set(f) { clics["pick:" + m[1]] = f; } }); return o; });
el("cat-res").querySelectorAll = (sel) => [...el("cat-res").innerHTML.matchAll(/data-genre="(\w+)" data-id="([^"]*)" data-titre="([^"]*)"/g)].map((m) => { const o = { dataset: { genre: m[1], id: m[2], titre: m[3] } }; Object.defineProperty(o, "onclick", { set(f) { clics["cat:" + m[2]] = f; } }); return o; });
const appels = [];
const REP = {
  "POST /api/ajout/appeler": { statut: 200, format: "json", delimiteur: "", items: "results", nb_items: 5, parametres_url: [{ nom: "q", valeur: "handball" }, { nom: "per_page", valeur: "5" }],
    parametre_requete: "q", mot_essai: "handball", echantillon: [{ champ: "nom_complet", valeur: "FENIX" }, { champ: "siege.libelle_commune", valeur: "TOULOUSE" }, { champ: "activite", valeur: "clubs" }, { champ: "siren", valeur: "422" }] },
  "POST /api/ajout/tester": { ok: true, total: 3, appels: 1, essai: "handball", noms: [{ nom: "FENIX", ville: "TOULOUSE", genre: "clubs", id: "422" }] },
  "POST /api/ajout/enregistrer": { id: "annuaire", fichier: "annuaire.yaml", active: false },
  "GET /api/ajout/catalogue?q=entreprises": { apis: [{ genre: "api", id: "A1", titre: "API Recherche d’Entreprises", organisation: "DINUM", base: "https://r.api.gouv.fr" }], jeux: [{ genre: "jeu", id: "J1", titre: "Liste des festivals", organisation: "Culture", nb_ressources: "1" }] },
  "GET /api/ajout/catalogue/api/A1": { base: "https://r.api.gouv.fr", points: [{ chemin: "/search", resume: "Recherche textuelle", parametre_requete: "q", parametres: [] }] },
};
const ctx = { document: doc, console, location: { origin: "https://x" }, localStorage: { getItem: () => null, setItem() {} }, CustomEvent: class {},
  fetch: async (u, o) => { const cle = (o?.method || "GET") + " " + u; appels.push([cle, o?.body]); const r = REP[cle]; return { ok: !!r, status: 404, json: async () => r ?? { detail: "inconnu" } }; } };
vm.createContext(ctx);
for (const f of ["static/commun.js", "static/ajout.js"]) vm.runInContext(fs.readFileSync(f, "utf8"), ctx);
const attendre = () => new Promise((r) => setTimeout(r, 40));
const bilan = [], ok = (n, b) => bilan.push([n, b]);
// ① catalogue : chercher, choisir une API, choisir sa recherche -> l'adresse est remplie et appelée
el("cat-q").value = "entreprises"; el("cat-go").onclick(); await attendre();
ok("catalogue : l'API et le jeu sont listés", el("cat-res").innerHTML.includes("API Recherche") && el("cat-res").innerHTML.includes("Liste des festivals"));
clics["cat:A1"](); await attendre();
ok("catalogue : la recherche textuelle est proposée", el("cat-res").innerHTML.includes("/search"));
// ② adresse collée
el("aj-url").value = "https://r.api.gouv.fr/search?q=handball&per_page=5";
el("aj-appeler").onclick(); await attendre();
ok("la réponse brute montre les champs à désigner", el("raw").innerHTML.includes('data-f="nom_complet"') && el("raw").innerHTML.includes("FENIX"));
ok("le mot d'essai vient de l'adresse", el("aj-mot").value === "handball");
ok("le paramètre des mots cherchés est proposé", el("aj-param").innerHTML.includes('value="q" selected'));
el("aj-param").value = "q"; // le navigateur lit l'option marquée « selected »
ok("Tester inactif tant qu'aucun nom n'est désigné", el("btn-test").disabled === true && el("btn-save").disabled === true);
clics["pick:nom_complet"](); clics["pick:siege.libelle_commune"]();
ok("les champs cliqués se rangent dans l'ordre : nom, ville", /nom_complet/.test(el("mapping").innerHTML) && /siege\.libelle_commune/.test(el("mapping").innerHTML));
ok("Tester actif, Enregistrer encore inactif (test obligatoire)", el("btn-test").disabled === false && el("btn-save").disabled === true);
el("aj-nom").value = "Annuaire des entreprises";
el("btn-test").onclick(); await attendre();
ok("l'essai montre les noms que grappes en tirerait", el("essai").innerHTML.includes("FENIX") && el("essai").innerHTML.includes("TOULOUSE"));
ok("après un test réussi, Enregistrer est actif", el("btn-save").disabled === false);
const corps = JSON.parse(appels.find(([k]) => k === "POST /api/ajout/tester")[1]);
ok("la spécification envoyée est complète", corps.spec.items === "results" && corps.spec.parametre_requete === "q" && corps.spec.champs.nom === "nom_complet" && corps.mot === "handball");
// changer un champ après le test redemande un test
clics["pick:nom_complet"]();
ok("modifier la prise après le test redemande un test", el("btn-save").disabled === true);
clics["pick:nom_complet"](); el("btn-test").onclick(); await attendre();
el("btn-save").onclick(); await attendre();
ok("enregistrement : dit que la prise est désactivée", /désactivée/.test(el("aj-ok").textContent) && /Réglages/.test(el("aj-ok").textContent));
for (const [n, b] of bilan) console.log((b ? "ok   " : "ÉCHEC ") + n);
process.exit(bilan.every(([, b]) => b) ? 0 : 1);
