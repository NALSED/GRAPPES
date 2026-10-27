// Réglages › Sources et Réglages › Outils (spécifications 05, 06, 10, 13).
import { h, icone } from "./dom.js";
import { agir, app, outilParId, recharger, sourceParId, sourcesDe } from "./etat.js";
import { AVERTISSEMENT_IA, COUTS, EFFETS, ETATS_OUTIL, ETATS_SOURCE, FIABILITES, ROLES, ROLES_ORDRE, ROLES_OUTIL, VERBES, aPluriel, fiabiliteParDefaut } from "./mots.js";
import { api, Refus } from "./api.js";
import { annoncer, avertissement, bouton, champ, etiquetteRole, groupePuces, ouvrirCouche, pastilleEtat, quotaVue, carteRepliable } from "./ui.js";

// ================================================================ Sources

export function pageSources() {
  const filtre = app.reglages.filtre.trim().toLowerCase();
  const cats = app.data.categories.map((c) => {
    const toutes = sourcesDe(c.id);
    const visibles = toutes.filter((s) => !s.retiree);
    const retirees = toutes.filter((s) => s.retiree);
    const lignes = filtre ? visibles.filter((s) => s.nom.toLowerCase().includes(filtre)) : visibles;
    return { ...c, visibles, retirees, lignes };
  });
  const cartes = cats
    .filter((c) => !filtre || c.lignes.length)
    .map((c) => {
      const ouverte = filtre ? true : app.reglages.ouverte === c.id;
      const allumees = c.visibles.filter((s) => s.etat !== "off").length;
      return carteRepliable({
        titre: c.nom,
        compte: `${aPluriel(c.visibles.length, "source", "sources")} · ${allumees} allumée${allumees > 1 ? "s" : ""}`,
        ouverte,
        onbascule: () => {
          app.reglages.ouverte = app.reglages.ouverte === c.id ? null : c.id;
          app.rendre();
        },
        corps: h("div", { class: "carte-corps liste" }, enteteColonnes(), c.lignes.map(ligneSource), c.retirees.length > 0 && retireesVue(c.retirees)),
      });
    });
  if (!cartes.length) return h("p", { class: "vide" }, "Aucune source ne porte ce nom.");
  return h("div", { class: "cartes" }, cartes);
}

function enteteColonnes() {
  const col = (cls, t) => h("span", { class: `${cls} etiquette-col` }, t);
  return h("div", { class: "ligne entete" }, col("c-etat", "État"), col("c-nom", "Nom"), col("c-cout", "Coût"), col("c-role", "Rôle"), col("c-quota", "Quota"), col("c-actions", "Actions"));
}

function ligneSource(s) {
  return h(
    "div",
    { class: "ligne", dataset: { source: s.id } },
    h("span", { class: "c-etat" }, pastilleEtat(s.etat, ETATS_SOURCE)),
    h("span", { class: "c-nom" }, h("span", { class: "fort" }, s.nom), h("span", { class: "legende pale" }, s.pays)),
    h("span", { class: "c-cout" }, h("span", { class: `cout ${s.cout}` }, s.cout)),
    h("span", { class: "c-role" }, etiquetteRole(s.role)),
    h("span", { class: "c-quota" }, quotaVue(s)),
    h(
      "span",
      { class: "c-actions" },
      bouton({ libelle: VERBES.modifier, icon: "modifier", petit: true, onclick: () => ficheSource(s.id), "aria-label": `${VERBES.modifier} ${s.nom}` }),
      bouton({ libelle: VERBES.retirer, icon: "retirer", variante: "danger", petit: true, onclick: () => retirerSource(s), "aria-label": `${VERBES.retirer} ${s.nom}` }),
    ),
  );
}

function retireesVue(retirees) {
  return h(
    "div",
    { class: "retirees" },
    h("span", { class: "legende" }, aPluriel(retirees.length, "source retirée", "sources retirées") + " :"),
    retirees.map((s) => bouton({ libelle: `${VERBES.ajouter} ${s.nom}`, icon: "ajouter", petit: true, onclick: () => agir(() => api.post(`/sources/${s.id}/rajouter`), { succes: `« ${s.nom} » est de retour dans la liste.` }) })),
  );
}

/** RETIRER : réversible, sans fenêtre, sans toucher à aucun fichier. */
function retirerSource(s) {
  return agir(() => api.post(`/sources/${s.id}/retirer`), { succes: `« ${s.nom} » est retirée de la liste. Rien n'est effacé : tu peux la remettre.` });
}

/** Allumer une source : l'avertissement de la source (prestataire payant, service à risque) se lit AVANT, puis la demande est refaite avec « confirme ». */
async function allumerSource(s) {
  try {
    const r = await api.post(`/sources/${s.id}/allumer`, {});
    await recharger();
    annoncer(r.etat === "ok" ? `« ${s.nom} » est allumée.` : `« ${s.nom} » est allumée, mais « ${ETATS_SOURCE[r.etat]} » : lance son test pour qu'elle devienne opérationnelle.`);
  } catch (e) {
    if (e instanceof Refus && e.statut === 409 && e.corps && e.corps.avertissements) {
      avertissement({
        titre: `${VERBES.allumer} « ${s.nom} » ?`, points: e.corps.avertissements.map((a) => a.texte), verbe: VERBES.allumer,
        onconfirmer: () => agir(() => api.post(`/sources/${s.id}/allumer`, { confirme: true }), { succes: `« ${s.nom} » est allumée.` }),
      });
    } else annoncer(e instanceof Refus ? e.message : "Quelque chose a échoué.", true);
  }
}

/** La fiche d'une source. Une source DÉCLARÉE (toutes celles de la liste) montre ce que sa déclaration dit, en lecture seule ; on ne change d'ici que
 *  ce que la suite ajoute (langue, rôle, catégorie), la clé, et l'état. Sans `id` : ajout d'une source API (fenêtre centrée de 600 px). */
export function ficheSource(id) {
  const edition = !!id;
  const s = edition ? sourceParId(id) : { nom: "", cat: null, role: null, cout: "gratuit", fiabilite: null, pays: "", langue: "", etat: "warn", quota: null, description: "", cle: false, cle_requise: false, tests: [], voyant: "" };
  const val = { cat: s.cat, role: s.role, cout: s.cout, fiabilite: edition ? s.fiabilite : null, auth: "bearer" };
  const fiabiliteVoulue = () => val.fiabilite || fiabiliteParDefaut(val.cat); // à la création : B pour une source officielle, D pour le web ou la presse, à ajuster une fois testée
  const lecture = (libelle, valeur) => h("div", { class: "champ" }, h("span", { class: "titre-champ" }, libelle), h("span", {}, valeur || "—"));
  const f = {
    nom: champ({ libelle: "Nom", valeur: s.nom, placeholder: "ex. Annuaire des clubs" }),
    pays: champ({ libelle: "Pays", valeur: s.pays, placeholder: "FR, UK, Mondial…" }),
    langue: champ({ libelle: "Langue", valeur: s.langue, placeholder: "fr, en, de…", aide: "La langue dans laquelle cette source attend les mots cherchés. L'Aide s'en sert pour signaler qu'une Traduction manque." }),
    desc: champ({ libelle: "Description", valeur: s.description, lignes: 3 }),
    cle: champ({ libelle: "Clé d'API", type: "password", autocomplete: "new-password", aide: s.cle ? "Pour la changer, saisis-en une nouvelle." : "Elle ne s'affiche plus une fois enregistrée." }),
    url: champ({ libelle: "Adresse de la source", placeholder: "https://…", aide: "Une source de type API : le service est interrogé en GET. Les autres types (serveur MCP, fichier, base, programme local, flux RSS) s'ajoutent dans l'ancienne page Ajout." }),
    requete: champ({ libelle: "Paramètre de la recherche", placeholder: "q", aide: "Le nom sous lequel la source reçoit ce qu'on cherche." }),
    champNom: champ({ libelle: "Champ du nom", placeholder: "title", aide: "Où se trouve le NOM dans chaque résultat de la réponse." }),
    liste: champ({ libelle: "Liste des résultats", placeholder: "items", aide: "Le chemin de la liste dans la réponse. Vide si la réponse est elle-même la liste." }),
    exemple: champ({ libelle: "Exemple de réponse", lignes: 5, code: true, obligatoire: true, aide: "Une vraie réponse du service. Le test la lit ; il n'appelle jamais la source." }),
    tarif: champ({ libelle: "Prix par appel (dollars)", placeholder: "0.005" }),
  };
  const zones = { cat: h("div", { class: "champ" }), role: h("div", { class: "champ" }), cout: h("div", { class: "champ" }), fiab: h("div", { class: "champ" }), auth: h("div", { class: "champ" }) };
  const manque = h("div", { class: "mot-manque", role: "status" });
  const principal = bouton({ libelle: edition ? VERBES.enregistrer : `${VERBES.ajouter} la source`, variante: "principal", onclick: valider });
  const catNom = (c) => app.data.categories.find((x) => x.id === c)?.nom;
  const ajoutCles = h("div", { class: "options-grille" }, f.url.el, h("div", { class: "deux-col" }, f.requete.el, f.champNom.el), f.liste.el, f.exemple.el);

  function dessiner() {
    zones.cat.replaceChildren(h("span", { class: "titre-champ" }, "Catégorie ", h("span", { class: "obligatoire" }, "obligatoire")), groupePuces(app.data.categories.map((c) => [c.id, c.nom]), val.cat, (v) => { val.cat = v; dessiner(); }));
    zones.role.replaceChildren(
      h("span", { class: "titre-champ" }, "Rôle ", h("span", { class: "obligatoire" }, "obligatoire")),
      groupePuces(ROLES_ORDRE.map((r) => [r, ROLES[r].nom]), val.role, (v) => { val.role = v; dessiner(); }),
      h("span", { class: "aide-champ" }, "CHERCHER, VÉRIFIER et ENRICHIR travaillent dans une catégorie. CATALOGUE, OUTIL et RAPPROCHER servent à toutes."),
    );
    if (!edition) {
      zones.cout.replaceChildren(h("span", { class: "titre-champ" }, "Coût"), groupePuces(COUTS.map((c) => [c, c]), val.cout, (v) => { val.cout = v; dessiner(); }));
      f.tarif.el.classList.toggle("cache", val.cout !== "payant");
      zones.auth.replaceChildren(h("span", { class: "titre-champ" }, "La clé s'envoie"), groupePuces([["bearer", "bearer"], ["header", "header"], ["basic", "basic"], ["query", "query"]], val.auth, (v) => { val.auth = v; dessiner(); }), h("span", { class: "aide-champ" }, "Seulement si tu colles une clé ci-dessous."));
    }
    zones.fiab.replaceChildren(
      h("span", { class: "titre-champ" }, "Fiabilité de la source"),
      groupePuces(FIABILITES.map(([l]) => [l, l]), fiabiliteVoulue(), (v) => { val.fiabilite = v; dessiner(); }),
      h("span", { class: "aide-champ" }, FIABILITES.find(([l]) => l === fiabiliteVoulue())[1]),
    );
    const pret = val.cat && val.role;
    principal.disabled = !edition && !pret;
    manque.textContent = !edition && !pret ? `Il manque ${!val.cat && !val.role ? "la catégorie et le rôle" : !val.cat ? "la catégorie" : "le rôle"}.` : "";
  }

  async function valider() {
    const corps = edition
      ? { cat: val.cat, role: val.role, langue: f.langue.valeur(), fiabilite: fiabiliteVoulue() }
      : { nom: f.nom.valeur(), cat: val.cat, role: val.role, cout: val.cout, fiabilite: fiabiliteVoulue(), pays: f.pays.valeur(), langue: f.langue.valeur(), description: f.desc.valeur(),
          url: f.url.valeur(), parametre_requete: f.requete.valeur(), champ_nom: f.champNom.valeur(), liste: f.liste.valeur(), exemple: f.exemple.valeur(), tarif: f.tarif.valeur(),
          cle_valeur: f.cle.valeur(), auth: val.auth };
    const res = await agir(() => (edition ? api.put(`/sources/${id}`, corps) : api.post("/sources", corps)), { rechargerApres: false });
    if (!res) return;
    if (edition && f.cle.valeur()) {
      const ok = await agir(() => api.put(`/sources/${id}/cle`, { valeur: f.cle.valeur() }), { rechargerApres: false });
      if (!ok) return;
    }
    f.cle.definir(""); // la clé ne reste jamais dans le champ
    await recharger(); // les données sont à jour AVANT que la fiche se ferme : la rouvrir tout de suite montre « clé enregistrée »
    couche.fermer();
    if (!edition) app.reglages.ouverte = val.cat;
    annoncer(edition ? `« ${s.nom} » est enregistrée.` : `« ${corps.nom} » est ajoutée, éteinte. Son test local a tourné : regarde son état dans la liste.`);
  }

  const tests = edition && h("div", { class: "champ" }, h("span", { class: "titre-champ" }, "Derniers tests"),
    h("div", { class: "options-grille" }, (s.tests.length ? s.tests : ["Pas encore testée."]).map((t) => h("span", { class: "legende" }, t))),
    h("span", { class: "legende" }, s.voyant),
    bouton({ libelle: `${VERBES.lancer} le test`, icon: "tester", petit: true, onclick: async () => {
      const r = await agir(() => api.post(`/sources/${id}/test`), { rechargerApres: true });
      if (!r) return;
      couche.fermer();
      annoncer(r.ok ? `Test local réussi : « ${s.nom} » (${ETATS_SOURCE[r.etat]}).` : `Test échoué : ${r.raisons.join(" ; ")}.`, !r.ok);
    } }));
  const interrupteur = edition && bouton({ libelle: s.etat === "off" ? VERBES.allumer : VERBES.eteindre, icon: "interrupteur", petit: true, onclick: async () => {
    couche.fermer();
    if (s.etat === "off") await allumerSource(s);
    else await agir(() => api.post(`/sources/${id}/eteindre`), { succes: `« ${s.nom} » est éteinte.` });
  } });

  const contenu = edition
    ? [
      lecture("Nom", s.nom), zones.cat, zones.role,
      h("div", { class: "deux-col" }, lecture("Coût", s.cout), lecture("Pays", s.pays)),
      zones.fiab,
      h("div", { class: "deux-col" }, f.langue.el, h("div", {})),
      h("div", { class: "deux-col" }, lecture("Quota", s.acces === "base_exterieure" ? "Base extérieure" : s.copie ? "Copie locale" : s.quota ? `${s.quota.utilise} / ${s.quota.plafond} · ${s.quota.unite}` : "illimité"), lecture("Adresse", s.domaine)),
      s.description && h("p", { class: "douce" }, s.description),
      lecture("Accès", s.acces === "base_exterieure" ? "Base extérieure" : s.copie ? "Copie locale" : "API"),
      s.acces === "base_exterieure" && lecture("Machine", s.machine), // une adresse et des identifiants, ni clé d'API, ni quota, ni date de copie
      s.acces === "base_exterieure" && h("span", { class: "legende" }, "identifiants enregistrés"),
      s.copie && lecture("Mise à jour", s.copie.installee ? s.copie.date : "copie non installée sur cette machine"),
      h("p", { class: "legende" }, "Le nom, le coût, le pays et le quota viennent de la déclaration de la source : ils ne se changent pas d'ici."),
      !s.copie && s.acces !== "base_exterieure" && s.cle_requise && f.cle.el, !s.copie && s.acces !== "base_exterieure" && s.cle_requise && s.cle && h("span", { class: "legende" }, "clé enregistrée"),
      h("div", { class: "champ" }, h("span", { class: "titre-champ" }, "État"), h("div", { class: "pied-boutons" }, pastilleEtat(s.etat, ETATS_SOURCE), interrupteur)),
      tests,
    ]
    : [
      f.nom.el, zones.cat, zones.role,
      h("div", { class: "deux-col" }, zones.cout, f.pays.el), f.tarif.el,
      h("div", { class: "deux-col" }, f.langue.el, h("div", {})), zones.fiab, ajoutCles, f.desc.el, f.cle.el, zones.auth,
      h("p", { class: "note" }, "Une nouvelle source est enregistrée éteinte, et son test local tourne tout de suite. Elle démarre « à vérifier » tant qu'il n'a pas réussi."),
    ];
  const pied = [
    manque,
    h("div", { class: "pied-boutons" }, principal, bouton({ libelle: VERBES.annuler, onclick: () => couche.fermer(true) }),
      edition && h("span", { class: "droite" }, bouton({ libelle: VERBES.retirer, icon: "retirer", variante: "danger", onclick: async () => { couche.fermer(); await retirerSource(s); } }))),
    edition && h("span", { class: "legende" }, "Retirer enlève la source de cette liste. Réglages, la déclaration et les fichiers ne bougent pas."),
  ];
  const couche = ouvrirCouche({
    cote: edition, titre: edition ? s.nom : "Nouvelle source",
    sous: edition ? [h("span", { class: `pastille ${s.etat}`, "aria-hidden": "true" }), `${catNom(s.cat)} · ${ETATS_SOURCE[s.etat]}`] : "Une source de type API",
    contenu, pied,
  });
  if (!edition) couche.boite.classList.add("fenetre");
  dessiner();
  return couche;
}

// ================================================================ Outils

export function pageOutils() {
  const visibles = app.data.outils.filter((o) => !o.retire);
  const retires = app.data.outils.filter((o) => o.retire);
  return h(
    "div",
    { class: "cartes" },
    h("p", { class: "douce" }, "Les outils transforment ou relient les résultats. Chaque outil allumé devient une brique que tu poses dans la Recherche avancée."),
    h("div", { class: "grille-outils" }, visibles.map(carteOutil)),
    retires.length > 0 && h("div", { class: "retirees" }, h("span", { class: "legende" }, aPluriel(retires.length, "outil retiré", "outils retirés") + " :"),
      retires.map((o) => bouton({ libelle: `${VERBES.ajouter} ${o.nom}`, icon: "ajouter", petit: true, onclick: () => agir(() => api.post(`/outils/${o.id}/rajouter`), { succes: `« ${o.nom} » est de retour dans la grille.` }) }))),
  );
}

function carteOutil(o) {
  const eteint = o.etat === "off";
  return h(
    "div",
    { class: "outil", dataset: { outil: o.id } },
    h("div", { class: "outil-tete" }, h("span", { class: "outil-nom" }, o.nom), etiquetteRole(o.role)),
    h("p", {}, o.fait),
    h("div", { class: "outil-pied" }, pastilleEtat(o.etat, ETATS_OUTIL),
      h("span", { class: "outil-actions" },
        bouton({ libelle: VERBES.modifier, icon: "modifier", petit: true, onclick: () => ficheOutil(o.id), "aria-label": `${VERBES.modifier} ${o.nom}` }),
        bouton({ libelle: eteint ? VERBES.allumer : VERBES.eteindre, icon: "interrupteur", petit: true, onclick: () => basculerOutil(o), "aria-label": `${eteint ? VERBES.allumer : VERBES.eteindre} ${o.nom}` }))),
  );
}

/** Allumer l'Assistant IA passe TOUJOURS par l'avertissement ; éteindre ne redemande rien (on n'avertit que dans le sens risqué). */
export function basculerOutil(o) {
  if (o.etat !== "off") return agir(() => api.post(`/outils/${o.id}/eteindre`), { succes: `« ${o.nom} » est éteint.` });
  if (o.id !== "ia") return agir(() => api.post(`/outils/${o.id}/allumer`), { succes: `« ${o.nom} » est allumé.` });
  return new Promise((resolve) => {
    avertissement({ titre: `${VERBES.allumer} « ${o.nom} » ?`, points: AVERTISSEMENT_IA, verbe: VERBES.allumer, onconfirmer: () => resolve(agir(() => api.post(`/outils/${o.id}/allumer`, { avertissement_lu: true }), { succes: `« ${o.nom} » est allumé. Tout ce qu'il produit reste marqué « IA ».` })) });
  });
}

const CODE_MODELE = 'def run(resultats):\n    # resultats : liste de dictionnaires\n    return [r for r in resultats if r.get("pays") == "FR"]';
const ENTREE_SCRIPT = '[{"nom": "Club A", "pays": "FR"}, {"nom": "Club B", "pays": "UK"}]';
const SORTIE_SCRIPT = '[{"nom": "Club A", "pays": "FR"}]';

/** La fiche d'un outil : panneau de 520 px pour modifier, fenêtre de 640 px pour ajouter. */
export function ficheOutil(id) {
  const edition = !!id;
  const o = edition ? outilParId(id) : { nom: "", nature: "modele", modele: null, role: "OUTIL", fait: "", recoit: "", renvoie: "", effet: "journal", options: [], code: CODE_MODELE, test_entree: "", test_sortie: "", etat: "warn", livre: false };
  const val = { nature: o.nature, modele: o.modele, role: o.role, effet: o.effet, options: o.options.map((p) => [...p]) };
  const f = {
    nom: champ({ libelle: "Nom de l'outil", valeur: o.nom, placeholder: "ex. Garder la France" }),
    code: champ({ libelle: "Ton script (Python)", valeur: o.code || CODE_MODELE, lignes: 7, code: true, aide: "Le script reçoit la liste des résultats et renvoie une liste. Il tourne dans un processus isolé : pas de réseau, 10 secondes au maximum." }),
    fait: champ({ libelle: "Ce qu'il fait", valeur: o.fait, placeholder: "Une phrase" }),
    recoit: champ({ libelle: "Ce qu'il reçoit", valeur: o.recoit }),
    renvoie: champ({ libelle: "Ce qu'il renvoie", valeur: o.renvoie }),
    entree: champ({ libelle: "Exemple d'entrée", valeur: o.test_entree, lignes: 3, code: true }),
    sortie: champ({ libelle: "Sortie attendue", valeur: o.test_sortie, lignes: 3, code: true }),
    cle: champ({ libelle: "Clé d'API", type: "password", autocomplete: "new-password", aide: o.cle ? "clé enregistrée — pour la changer, saisis-en une nouvelle." : "Elle ne s'affiche plus une fois enregistrée." }),
  };
  const zones = { nature: h("div", { class: "champ" }), modele: h("div", { class: "champ" }), options: h("div", { class: "champ" }), role: h("div", { class: "champ" }), effet: h("div", { class: "champ" }), test: h("div", { class: "champ" }) };
  let champsOptions = [];
  // Les options sont des champs qui gardent leur valeur entre deux redessins : on les recrée seulement quand le modèle change.
  const reconstruireOptions = () => { champsOptions = val.options.map(([lib, v]) => champ({ libelle: lib, valeur: v })); };
  reconstruireOptions();
  const manque = h("div", { class: "mot-manque", role: "status" });
  const principal = bouton({ libelle: edition ? VERBES.enregistrer : `${VERBES.ajouter} l'outil`, variante: "principal", onclick: valider });
  const resultatTest = h("div", { class: "sortie-test", "aria-live": "polite" });

  function dessiner() {
    const script = val.nature === "script";
    zones.nature.replaceChildren(h("span", { class: "titre-champ" }, "Comment il travaille"), groupePuces([["modele", "À partir d'un modèle"], ["script", "Script collé"]], val.nature, (v) => {
      val.nature = v;
      if (v === "script" && !f.entree.valeur().trim()) { f.entree.definir(ENTREE_SCRIPT); f.sortie.definir(SORTIE_SCRIPT); }
      dessiner();
    }));
    zones.modele.replaceChildren(...(script ? [] : [h("span", { class: "titre-champ" }, "Modèle"), groupePuces(app.data.outils.filter((m) => m.livre).map((m) => [m.id, m.nom]), val.modele, (v) => {
      const m = outilParId(v);
      val.modele = v; val.role = m.role; val.effet = m.effet; val.options = m.options.map((p) => [...p]); reconstruireOptions();
      f.fait.definir(m.fait); f.recoit.definir(m.recoit); f.renvoie.definir(m.renvoie); f.entree.definir(m.test_entree); f.sortie.definir(m.test_sortie);
      dessiner();
    })]));
    zones.options.replaceChildren(...(script || !champsOptions.length ? [] : [h("span", { class: "titre-champ" }, "Réglages du modèle"), h("div", { class: "options-grille" }, champsOptions.map((c) => c.el))]));
    zones.role.replaceChildren(h("span", { class: "titre-champ" }, "Rôle"), groupePuces(ROLES_OUTIL.map((r) => [r, ROLES[r].nom]), val.role, (v) => { val.role = v; dessiner(); }));
    zones.effet.replaceChildren(h("span", { class: "titre-champ" }, "Effet dans le Tableau de bord"), groupePuces(EFFETS.map(([k, l]) => [k, l]), val.effet, (v) => { val.effet = v; dessiner(); }), h("span", { class: "aide-champ" }, EFFETS.find((e) => e[0] === val.effet)[2]));
    f.code.el.classList.toggle("cache", !script);
    const pret = script || !!val.modele;
    principal.disabled = !edition && !pret;
    manque.textContent = !edition && !pret ? "Choisis un modèle." : "";
  }
  function corps() {
    return {
      nom: f.nom.valeur(), nature: val.nature, modele: val.nature === "modele" ? val.modele : null, role: val.role, effet: val.effet, fait: f.fait.valeur(), recoit: f.recoit.valeur(), renvoie: f.renvoie.valeur(),
      options: val.options.map(([lib], i) => [lib, champsOptions[i] ? champsOptions[i].valeur() : val.options[i][1]]), code: f.code.valeur(), test_entree: f.entree.valeur(), test_sortie: f.sortie.valeur(),
    };
  }
  async function enregistrer() {
    const res = await agir(() => (edition ? api.put(`/outils/${id}`, corps()) : api.post("/outils", corps())), { rechargerApres: false });
    if (!res) return null;
    const cle = f.cle.valeur();
    if (cle) { await agir(() => api.put(`/outils/${res.id || id}/cle`, { valeur: cle }), { rechargerApres: false }); f.cle.definir(""); }
    return res.id || id;
  }
  async function valider() {
    const ident = await enregistrer();
    if (!ident) return;
    await recharger();
    couche.fermer();
    annoncer(edition ? `« ${f.nom.valeur()} » est enregistré.` : `« ${f.nom.valeur()} » est ajouté. Il démarre « à vérifier » jusqu'à son premier test réussi.`);
  }
  async function tester() {
    const ident = await enregistrer(); // le test porte sur ce qui est écrit à l'écran, pas sur l'ancienne version
    if (!ident) return;
    const r = await agir(() => api.post(`/outils/${ident}/test`), { rechargerApres: true });
    if (!r) return;
    resultatTest.textContent = r.ok ? `${r.execute ? "Sortie obtenue" : "Fiche vérifiée (l'outil ne s'exécute pas encore sur de vraies données)"} :\n${r.sortie}` : `Test échoué : ${r.raisons.join(" ; ")}`;
    annoncer(r.ok ? "Test réussi : l'outil est opérationnel." : "Test échoué.", !r.ok);
  }

  const contenu = [
    f.nom.el, zones.nature, zones.modele, zones.options, f.code.el, f.fait.el,
    h("div", { class: "deux-col" }, f.recoit.el, f.renvoie.el), zones.role, zones.effet,
    h("div", { class: "champ" }, h("span", { class: "titre-champ" }, "Test sur un exemple"), h("div", { class: "deux-col" }, f.entree.el, f.sortie.el), bouton({ libelle: `${VERBES.lancer} le test`, icon: "tester", petit: true, onclick: tester }), resultatTest,
      h("span", { class: "aide-champ" }, "L'outil passe « opérationnel » après un test réussi.")),
    f.cle.el,
  ];
  const pied = [manque, h("div", { class: "pied-boutons" }, principal, bouton({ libelle: VERBES.annuler, onclick: () => couche.fermer(true) }),
    edition && h("span", { class: "droite" }, bouton({ libelle: VERBES.retirer, icon: "retirer", variante: "danger", onclick: async () => { couche.fermer(); await agir(() => api.post(`/outils/${id}/retirer`), { succes: `« ${o.nom} » est retiré de la grille. Rien n'est effacé : tu peux le remettre.` }); } })))];
  const couche = ouvrirCouche({ cote: edition, largeur: edition ? "large" : "w640", titre: edition ? o.nom : "Nouvel outil", sous: edition ? [h("span", { class: `pastille ${o.etat}`, "aria-hidden": "true" }), `${o.nature === "script" ? "Script" : "Modèle"} · ${ETATS_OUTIL[o.etat]}`] : "Choisis un modèle ou colle un script", contenu, pied });
  dessiner();
  return couche;
}

export { Refus };
