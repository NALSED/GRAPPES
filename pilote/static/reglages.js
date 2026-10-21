/* Page Réglages (fiche 01) : sources, vérification, sortie, budget, presets. Chaque bloc est repliable (état mémorisé). Montre le DERNIER ÉTAT CONNU avec sa date ;
   n'appelle aucun service externe. Une clé n'est jamais reçue ici : seulement « présente » ou « absente ». */
"use strict";
(function(){
  var D=null, famSel={1:"TOUT",2:"TOUT",3:"TOUT"};
  var PARTIE={1:"recherche",2:"verification",3:"sortie"};
  var TXT_ACTIF="Vérification active — les noms sont recoupés entre plusieurs sources.";
  var TXT_COUPEE="<b>Vérification coupée</b> — le résultat sort brut, sans recoupement. Dans Tri, le nombre d'endroits n'est plus compté et la fiabilité est marquée « non mesurée ».";
  var NOM_PARTIE={1:"sources",2:"vérification"};

  /* ---- menus repliables : un bloc replié montre son intitulé, son état et un rappel court ; l'état ouvert/fermé est mémorisé ---- */
  function cleBloc(d){return "g_bloc_"+d.dataset.bloc}
  document.querySelectorAll("details.bloc").forEach(function(d){
    try{if(localStorage.getItem(cleBloc(d))==="1")d.open=true}catch(e){}
    d.addEventListener("toggle",function(){try{localStorage.setItem(cleBloc(d),d.open?"1":"0")}catch(e){}});
  });
  function resume(id,etat,rappel){
    var e=el("e-"+id),r=el("r-"+id);
    if(e)e.textContent=etat||"";if(r)r.textContent=rappel||"";
  }

  function el(id){return document.getElementById(id)}
  function erreur(msg){var e=el("reglages-erreur");e.style.display=msg?"block":"none";e.textContent=msg||""}
  /* Les changements partent UN À LA FOIS, dans l'ordre : le serveur lit puis réécrit le fichier de réglages, donc deux envois
     qui se recouvrent se recouvraient aussi dans le fichier et le premier était perdu sans un mot. */
  var fileAttente=Promise.resolve();
  function file(f){
    var suite=fileAttente.then(f,f);
    fileAttente=suite.catch(function(){});  /* un changement refusé n'empêche pas le suivant */
    return suite;
  }
  /* le rond de la ligne vient du serveur : vert = disponible et utilisable, orange = il manque quelque chose, rouge = inutilisable */
  function point(s){return s.voyant||["off","pas encore testée"]}
  function envoyerSource(id,corps){
    return file(function(){
      return envoyerConfirme("/api/reglages/source/"+encodeURIComponent(id),"PUT",corps).then(function(){erreur("");return charger()})
        .catch(function(e){erreur("Le changement est refusé : "+e.message);return charger()});
    });
  }

  var BTN='style="font-size:11.5px;padding:3px 8px"';
  function ligneSource(s,p){
    var pt=point(s), role=p===1?"chercher":"verifier", coche=s[role];
    var cle=s.cle_requise?'<span class="smeta" style="display:block">Clé d’API : <b>'+(s.cle==="presente"?"présente":"absente")+"</b></span>":"";
    /* où la source écrit (F17-4a) : connu seulement pour une source « api » ou « mcp » déclarée ; une source du catalogue l'a dans du code revu */
    var domaine=s.domaine?'<span class="smeta" style="display:block">Domaine : <b>'+esc(s.domaine)+"</b></span>":"";
    var avert=s.avertissement?'<span class="smeta" style="display:block"><b>Attention :</b> '+esc(s.avertissement)+"</span>":"";
    /* la ligne ne garde que le nom et gratuite / payante ; tout le reste (ce que la source trouve, son état, son coût, ses tests) est dans « Détails » */
    var det='<details style="margin-top:4px"><summary class="smeta" style="cursor:pointer">Détails, coût, tests</summary>'
      +'<span class="smeta" style="white-space:normal;display:block;margin-top:4px">'+esc(s.trouve)+" — "+esc(s.pays.join(", "))+" — "+esc(s.main_phrase)+" — "+esc(s.cout_phrase)+"</span>"
      +'<span class="smeta" style="white-space:normal;display:block">'+esc(s.etat_phrase)+"</span>"+cle+domaine+avert
      +'<div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap;align-items:center"><button class="btn" data-tester="'+esc(s.id)+'" '+BTN+'>Tester (gratuit, sans appel)</button>'
      +'<button class="btn" data-reel="'+esc(s.id)+'" '+BTN+'>Test réel…</button>'
      +(/En pause/.test(s.etat_phrase)?'<button class="btn" data-reprendre="'+esc(s.id)+'" '+BTN+'>Remettre en service</button>':"")
      +'<span class="smeta" data-msg="'+esc(s.id)+'" style="white-space:normal"></span></div><div class="form" style="margin-top:6px">'
      +'<div><label class="fl">Unité du coût</label><input class="inp" data-k="unite" data-id="'+esc(s.id)+'" value="'+esc(s.cout_effectif.unite)+'"></div>'
      +'<div><label class="fl">Valeur d’une unité en dollars</label><input class="inp" type="number" min="0" step="any" data-k="vers_dollar" data-id="'+esc(s.id)+'" value="'+s.cout_effectif.vers_dollar+'"></div>'
      +'<div><label class="fl">Unités par appel</label><input class="inp" type="number" min="0" step="any" data-k="par_appel" data-id="'+esc(s.id)+'" value="'+s.cout_effectif.par_appel+'"></div>'
      +'<div><label class="fl">Unités gratuites par mois</label><input class="inp" type="number" min="0" step="any" data-k="gratuit_par_mois" data-id="'+esc(s.id)+'" value="'+s.cout_effectif.gratuit_par_mois+'"></div>'
      +'<div><label class="fl">Niveau de confiance (0 à 1)</label><input class="inp" type="number" min="0" max="1" step="0.05" data-k="confiance" data-id="'+esc(s.id)+'" value="'+s.confiance+'"></div>'
      +'<div style="align-self:end"><button class="btn" data-cout="'+esc(s.id)+'">Enregistrer</button></div></div></details>';
    return '<div class="srow" style="align-items:flex-start"><span class="dot '+pt[0]+'" title="'+esc(pt[1])+'" style="margin-top:6px"></span>'
      +'<span style="font:500 10px var(--mono);color:var(--faint);width:52px;flex:none;margin-top:3px">'+esc(s.famille)+"</span>"
      +'<span class="sgrow"><span class="sname">'+esc(s.nom)+'<span class="prix">'+(s.gratuite?"gratuite":"payante")+"</span></span>"+det+"</span>"
      +'<label class="sw" title="'+(p===1?"utiliser pour chercher":"utiliser pour vérifier")+'" style="margin-top:3px"><input type="checkbox" data-p="'+p+'" data-id="'+esc(s.id)+'"'+(coche?" checked":"")+"><i></i><b></b></label>"
      +'<button class="retirer" data-retirer="'+esc(s.id)+'" title="Retirer de cette liste (rien n’est supprimé sur le disque)" aria-label="Retirer '+esc(s.nom)+'">✕</button></div>';
  }
  var PHRASE_CONTENU={nom:"les noms",tsites:"nom;ville;pays (trouver-sites)",detail:"le détail"};
  function ligneFormat(f){
    var cs=f.contenus.length>1?'<span class="smeta" style="display:block">Contenu : '+f.contenus.map(function(c){
      return '<label style="margin-right:12px"><input type="checkbox" data-fc="'+esc(f.id)+'" data-c="'+esc(c)+'"'+(f.contenus_choisis.indexOf(c)>=0?" checked":"")+"> "+esc(PHRASE_CONTENU[c]||c)+"</label>"}).join("")+"</span>":"";
    return '<div class="srow" style="align-items:flex-start"><span class="dot ok" title="disponible" style="margin-top:6px"></span><span style="font:500 10px var(--mono);color:var(--faint);width:52px;flex:none;margin-top:3px">'+esc(f.famille)+"</span>"
      +'<span class="sgrow"><span class="sname" title="'+esc(f.description)+'">'+esc(f.nom)+(f.perso?'<span class="prix">ajouté</span>':"")+"</span>"+cs+"</span>"
      +'<label class="sw"><input type="checkbox" data-p="3" data-id="'+esc(f.id)+'"'+(f.actif?" checked":"")+"><i></i><b></b></label></div>";
  }

  function rendrePresets(){
    el("presets").innerHTML=D.presets.map(function(c){
      var coche=D.presets_coches.indexOf(c.id)>=0;
      return '<div class="srow" style="align-items:flex-start;flex-wrap:wrap"><label class="sw" style="margin-top:3px"><input type="checkbox" data-preset="'+esc(c.id)+'"'+(coche?" checked":"")+"><i></i><b></b></label>"
        +'<span class="sgrow"><span class="sname">'+esc(c.nom)+(c.perso?'<span class="prix">ajouté</span>':"")+"</span>"
        +'<span class="smeta" style="white-space:normal">'+esc(c.phrase)+"</span>"
        +'<span class="smeta" style="white-space:normal">Sources : '+(c.sources.length?c.sources.map(function(s){return (s.allumee_par_defaut?"":"(")+esc(s.nom)+(s.allumee_par_defaut?"":" — éteinte)")}).join(", "):"aucune")+" — "+esc(c.cout)+"</span></span>"
        +'<button class="btn" data-perso="'+esc(c.id)+'" style="font-size:11.5px;padding:3px 8px">Personnaliser à partir de ce preset</button>'
        +(c.perso?'<span style="display:flex;gap:6px;flex-basis:100%;margin:6px 0 0 24px;flex-wrap:wrap"><button class="btn" data-infos="'+esc(c.id)+'" style="font-size:11.5px;padding:3px 8px">Modifier le nom et la description</button><button class="btn" data-choisir="'+esc(c.id)+'" style="font-size:11.5px;padding:3px 8px">Choisir les sources</button>'
          +'<a class="btn" href="/api/presets/'+encodeURIComponent(c.id)+'/export" download style="font-size:11.5px;padding:3px 8px">Exporter (sans clés)</a>'
          +'<button class="btn" data-suppr="'+esc(c.id)+'" style="font-size:11.5px;padding:3px 8px">Supprimer</button></span><div class="smeta" id="infos-'+esc(c.id)+'" style="flex-basis:100%;margin:6px 0 0 24px"></div><div class="smeta" id="choix-'+esc(c.id)+'" style="flex-basis:100%;margin:6px 0 0 24px"></div>':"")+"</div>"}).join("");
    el("presets").querySelectorAll("input[data-preset]").forEach(function(i){i.onchange=function(){
      var cs=[].slice.call(el("presets").querySelectorAll("input[data-preset]")).filter(function(x){return x.checked}).map(function(x){return x.dataset.preset});
      file(function(){return envoyer("/api/reglages/presets","PUT",{coches:cs}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message);return charger()})})}});
    el("presets").querySelectorAll("button[data-perso]").forEach(function(b){b.onclick=function(){
      var nom=window.prompt("Nom de ta copie modifiable de ce preset :");if(!nom)return;
      envoyer("/api/presets/personnaliser","POST",{depuis:b.dataset.perso,nom:nom}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message)})}});
    el("presets").querySelectorAll("button[data-infos]").forEach(function(b){b.onclick=function(){infosPreset(b.dataset.infos)}});
    el("presets").querySelectorAll("button[data-choisir]").forEach(function(b){b.onclick=function(){choixSources(b.dataset.choisir)}});
    el("presets").querySelectorAll("button[data-suppr]").forEach(function(b){b.onclick=function(){
      if(!window.confirm("Supprimer ce preset ? Les sources, elles, restent."))return;
      api("/api/presets/"+encodeURIComponent(b.dataset.suppr),{method:"DELETE"}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message)})}});
  }
  el("preset-vide").onclick=function(){
    var nom=window.prompt("Nom du nouveau preset (il part sans aucune source) :");if(!nom)return;
    envoyer("/api/presets","POST",{nom:nom}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message)})};
  el("preset-importer").onclick=function(){el("preset-fichier").click()};
  el("preset-fichier").onchange=function(){
    var f=el("preset-fichier").files&&el("preset-fichier").files[0];if(!f)return;
    f.text().then(function(t){return envoyer("/api/presets/importer","POST",{texte:t})}).then(function(r){
      el("preset-info").textContent="Importé : « "+r.nom+" » — "+r.ajoutees.length+" source(s) ajoutée(s), éteintes"+(r.en_attente_de_cle.length?" ; en attente de clé : "+r.en_attente_de_cle.join(", "):"")+(r.ignorees.length?" ; "+r.ignorees.length+" ignorée(s) (programme local)":"")+".";
      /* F17-4b : signalé en gros, jamais en silence — une source importée peut réclamer une clé que vous avez déjà, et l'envoyer où elle veut */
      if(r.cles_deja_presentes&&r.cles_deja_presentes.length)window.alert("Attention : "+r.cles_deja_presentes.length+" source(s) importée(s) réclame(nt) une clé que vous avez déjà ("
        +r.cles_deja_presentes.map(function(x){return x.source+" : "+(Array.isArray(x.cle)?x.cle.join(", "):x.cle)}).join(" ; ")
        +"). Vérifiez le domaine de chacune (Réglages > Détails) avant de l'activer : rien ne garantit qu'elle envoie votre clé au bon endroit.");
      erreur("");return charger()}).catch(function(e){erreur(e.message)})};

  /* Nom et description d'un preset personnalisé : l'identifiant ne change pas, donc le preset reste coché là où il l'était. */
  function infosPreset(id){
    var c=D.presets.filter(function(x){return x.id===id})[0],zone=el("infos-"+id);
    if(zone.innerHTML){zone.innerHTML="";return}
    zone.innerHTML='<div class="form" style="margin:0"><div><label class="fl" for="pn-'+esc(id)+'">Nom</label><input class="inp" id="pn-'+esc(id)+'" value="'+esc(c.nom)+'"></div>'
      +'<div><label class="fl" for="pd-'+esc(id)+'">Description</label><input class="inp" id="pd-'+esc(id)+'" value="'+esc(c.phrase_perso||"")+'" placeholder="une phrase qui dit à quoi sert ce preset"></div></div>'
      +'<div style="margin-top:6px"><button class="btn" data-enreg-infos="'+esc(id)+'" style="font-size:11.5px;padding:3px 8px">Enregistrer</button></div>';
    zone.querySelector("button[data-enreg-infos]").onclick=function(){
      /* lus au clic */
      var corps={nom:el("pn-"+id).value,phrase:el("pd-"+id).value};
      file(function(){return envoyer("/api/presets/"+encodeURIComponent(id)+"/infos","PUT",corps).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message)})})};
  }
  function choixSources(id){
    var c=D.presets.filter(function(x){return x.id===id})[0],zone=el("choix-"+id);
    if(zone.innerHTML){zone.innerHTML="";return}
    var dedans=c.sources.map(function(x){return x.id}),tout={};
    ["recherche"].forEach(function(k){(D.parties[k]||[]).forEach(function(s){if(s.id&&s.nom)tout[s.id]=s.nom})});
    zone.innerHTML=Object.keys(tout).sort().map(function(k){return '<label style="display:inline-block;margin:0 12px 4px 0"><input type="checkbox" data-src="'+esc(k)+'"'+(dedans.indexOf(k)>=0?" checked":"")+"> "+esc(tout[k])+"</label>"}).join("")
      +'<div><button class="btn" data-enreg="'+esc(id)+'" style="font-size:11.5px;padding:3px 8px">Enregistrer ces sources</button></div>';
    zone.querySelector("button[data-enreg]").onclick=function(){
      var cs=[].slice.call(zone.querySelectorAll("input[data-src]")).filter(function(x){return x.checked}).map(function(x){return x.dataset.src});
      envoyer("/api/presets/"+encodeURIComponent(id),"PUT",{sources:cs}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message)})};
  }

  var PHRASE_ACCES={api:"API",fichier:"fichier à télécharger",site:"site à consulter"};
  function rendreCatalogue(){
    var pays=el("cat-pays").value.trim().toUpperCase();
    if(!pays){el("cat-liste").textContent="";return}
    api("/api/catalogue-pays?pays="+encodeURIComponent(pays)).then(function(r){
      if(!r.trouve){el("cat-liste").innerHTML='<span class="smeta" style="white-space:normal">'+esc(r.message)+"</span>";return}
      el("cat-liste").innerHTML=r.bases.map(function(b){
        return '<div class="srow" style="align-items:flex-start"><span class="dot '+(b.coche?"ok":"off")+'" style="margin-top:6px"></span><span class="sgrow"><span class="sname">'+esc(b.nom)+'</span>'
          +'<span class="smeta" style="white-space:normal">'+esc(b.contenu)+" — "+esc(PHRASE_ACCES[b.acces]||b.acces)+" — licence : "+esc(b.licence)+" — vérifiée le "+esc(b.verifie_le)+"</span>"
          +'<span class="smeta"><a href="'+esc(b.url)+'" target="_blank" rel="noopener">'+esc(b.url)+"</a></span>"
          +(b.telechargeable?'<span class="smeta">'+((b.zones||[]).length?'<select data-zone="'+esc(b.id)+'" style="font-size:11.5px"><option value="">'+esc(r.nom)+' entière</option>'+b.zones.map(function(z){return '<option value="'+esc(z.id)+'">'+esc(z.nom)+"</option>"}).join("")+"</select> ":"")+'<button class="btn" data-taille="'+esc(b.id)+'" data-pays="'+esc(r.pays)+'" style="font-size:11.5px;padding:3px 8px">Demander le poids</button> <button class="btn" data-copie="'+esc(b.id)+'" data-pays="'+esc(r.pays)+'" style="font-size:11.5px;padding:3px 8px">Télécharger une copie locale…</button> <span data-poids></span></span>':"")+"</span></div>"}).join("");
      el("cat-liste").querySelectorAll("button[data-copie]").forEach(function(bt){bt.onclick=function(){
        var sz=bt.parentNode.querySelector("select[data-zone]"), zone=sz?sz.value:"";
        api("/api/copies-locales/proposition?pays="+encodeURIComponent(bt.dataset.pays)+"&base="+encodeURIComponent(bt.dataset.copie)+"&zone="+encodeURIComponent(zone)).then(function(p){
          if(!p.tient){window.alert("Pas assez de place : "+p.poids+" à télécharger, "+p.libre+" libres (10 % de marge exigés). Rien n'est téléchargé.");return}
          if(!window.confirm("Télécharger "+(p.zone?"la zone « "+p.zone+" » (copie PARTIELLE), ":"")+p.poids+" depuis "+p.adresse+" ?\nPlace libre : "+p.libre+".\nLicence : "+p.licence+".\nCela peut prendre du temps."))return;
          bt.disabled=true;bt.textContent="Téléchargement…";
          return envoyer("/api/copies-locales","POST",{pays:bt.dataset.pays,base:bt.dataset.copie,zone:zone,confirme:true}).then(function(){chargerCopies()})
        }).catch(function(e){window.alert(e.message)}).then(function(){bt.disabled=false;bt.textContent="Télécharger une copie locale…"})}});
      el("cat-liste").querySelectorAll("button[data-taille]").forEach(function(bt){bt.onclick=function(){
        var cible=bt.parentNode.querySelector("[data-poids]"), sz=bt.parentNode.querySelector("select[data-zone]");cible.textContent="…";
        api("/api/copies-locales/proposition?pays="+encodeURIComponent(bt.dataset.pays)+"&base="+encodeURIComponent(bt.dataset.taille)+"&zone="+encodeURIComponent(sz?sz.value:"")).then(function(t){
          cible.textContent=t.poids+(t.tient?" — place libre : "+t.libre:" — plus que la place libre sur le disque ("+t.libre+")")}).catch(function(e){cible.textContent=e.message})}});
    }).catch(function(e){el("cat-liste").textContent=e.message});
  }
  function chargerCopies(){
    api("/api/copies-locales").then(function(r){
      var pays=r.copies.map(function(c){return c.pays}).filter(function(x,i,l){return x&&l.indexOf(x)===i});
      resume("copies",r.copies.length?r.copies.length+" copie"+(r.copies.length>1?"s":""):"Aucune",(pays.length?pays.join(", ")+" · ":"")+"place libre "+r.disque_libre);
      el("cop-liste").innerHTML=r.copies.length?r.copies.map(function(c){
        return '<div class="srow"><span class="sgrow"><span class="sname">'+esc(c.nom)+" — "+esc(c.phrase)+'</span><span class="smeta">téléchargée le '+esc(c.telechargee_le.slice(0,10))+" ("+c.age_jours+" jours)"+(c.a_mettre_a_jour?" — <b>à mettre à jour</b>":"")+'</span></span>'
          +'<button class="btn" data-cop-suppr="'+esc(c.id)+'" style="font-size:11.5px;padding:3px 8px">Supprimer</button></div>'}).join("")+'<div class="smeta">Place libre : '+esc(r.disque_libre)+"</div>":'<span class="smeta">Aucune copie locale. Place libre : '+esc(r.disque_libre)+"</span>";
      el("cop-liste").querySelectorAll("button[data-cop-suppr]").forEach(function(b){b.onclick=function(){
        if(!window.confirm("Supprimer cette copie locale (le fichier est effacé du disque) ?"))return;
        api("/api/copies-locales/"+encodeURIComponent(b.dataset.copSuppr),{method:"DELETE"}).then(chargerCopies).catch(function(e){window.alert(e.message)})}});
    }).catch(function(e){el("cop-liste").textContent=e.message});
  }
  /* « Ajouter une source » : soit une source déjà enregistrée et prête (tableau), soit une nouvelle (page Ajout, avec le type et la clé). */
  var ouvertAjout={1:false,2:false};
  function dessinerAjouts(p){
    var z=el("ajouts"+p),part=PARTIE[p],role=p===1?"chercher":"verifier";
    var dispo=(D.parties[part]||[]).filter(function(s){return s.masquee&&s.masquee[part]&&s.voyant&&s.voyant[0]==="ok"&&s.roles.indexOf(role)>=0});
    var h='<button class="btn petit" data-existante="'+p+'">Ajouter une source existante'+(dispo.length?" ("+dispo.length+")":"")+'</button>'
      +'<button class="btn petit" data-nouvelle="'+p+'">Ajouter une nouvelle source…</button>';
    if(ouvertAjout[p]){
      h+='<div class="tableau">'+(dispo.length?dispo.map(function(s){
        return '<div class="srow"><span class="dot ok" title="'+esc(s.voyant[1])+'"></span><span style="font:500 10px var(--mono);color:var(--faint);width:52px;flex:none">'+esc(s.famille)+'</span>'
          +'<span class="sgrow"><span class="sname">'+esc(s.nom)+'<span class="prix">'+(s.gratuite?"gratuite":"payante")+"</span></span></span>"
          +'<button class="btn petit" data-remettre="'+esc(s.id)+'">Ajouter</button></div>'}).join("")
        :'<div class="srow"><span class="smeta" style="white-space:normal">Aucune source enregistrée n’attend d’être ajoutée. Ne figurent ici que les sources prêtes à l’emploi : sans clé manquante, avec leur adaptateur, et pas déjà affichées.</span></div>')+"</div>";
    }
    z.innerHTML=h;
    var be=z.querySelector("button[data-existante]");
    if(be)be.onclick=function(){ouvertAjout[p]=!ouvertAjout[p];dessinerAjouts(p)};
    var bn=z.querySelector("button[data-nouvelle]");
    if(bn)bn.onclick=function(){
      var onglet=document.querySelector('.tab[data-p="ajout"]');
      if(onglet)onglet.click();
      document.dispatchEvent(new CustomEvent("ajout-nouvelle",{detail:{verifier:p===2}}));
    };
    z.querySelectorAll("button[data-remettre]").forEach(function(b){b.onclick=function(){
      file(function(){return envoyer("/api/reglages/source/"+encodeURIComponent(b.dataset.remettre)+"/afficher","POST",{partie:part}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message);return charger()})})}});
  }
  function rendre(){
    if(!D)return;
    var pb=el("reglages-problemes");
    pb.innerHTML=D.problemes.length?'<div class="verif-off" style="border:1px solid var(--line2);border-radius:6px;margin-bottom:12px;display:block">'
      +D.problemes.map(function(x){return "<div><b>"+esc(x.fichier)+"</b> — "+esc(x.raison)+"</div>"}).join("")+"</div>":"";
    el("budget-plafond").value=D.budget.plafond_mensuel_usd;
    el("budget-etat").textContent="Dépensé ce mois : "+D.budget.depense_du_mois_usd.toFixed(2).replace(".",",")+" $ — reste "+D.budget.reste_usd.toFixed(2).replace(".",",")+" $"+(D.budget.atteint?" — plafond atteint : seules les sources gratuites sont utilisées":"");
    var fr=function(x){return x.toFixed(2).replace(".",",")};
    resume("budget",D.budget.atteint?"Plafond atteint":"Dans la limite","plafond "+fr(D.budget.plafond_mensuel_usd)+" $ par mois · dépensé "+fr(D.budget.depense_du_mois_usd)+" $");
    resume("assistant",D.assistant.termine?"Terminé":"À faire","rouvrir une étape : sources, vérification, sortie");
    var coches=D.presets.filter(function(c){return D.presets_coches.indexOf(c.id)>=0}).map(function(c){return c.nom});
    resume("presets",D.presets_coches.length+" coché"+(D.presets_coches.length>1?"s":""),coches.length?coches.join(", "):"aucun preset coché · "+D.presets.length+" proposés");
    resume("bases","Catalogue",(D.catalogue_nb_pays||0)+" pays connus · rien n'est téléchargé d'ici");
    rendrePresets();
    chargerCopies();
    if(!el("cat-pays").value&&D.pays){el("cat-pays").value=D.pays;rendreCatalogue()}
    [1,2,3].forEach(function(p){
      var tout=(D.parties[PARTIE[p]]||[]).filter(function(s){return p===3||!(s.masquee&&s.masquee[PARTIE[p]])});
      var actives=tout.filter(function(s){return p===3?s.actif:(p===1?s.chercher:s.verifier)}).length;
      el("c"+p).textContent=actives+" / "+tout.length+" actives";
      var pretes=tout.filter(function(s){return s.voyant&&s.voyant[0]==="ok"}).length;
      if(p===1)el("e1").textContent=actives+" active"+(actives>1?"s":"");
      if(p===2)el("e2").textContent=D.verification.active?"Active":"Coupée";
      if(p===3){var fa=tout.filter(function(f){return f.actif}).map(function(f){return f.id});el("e3").textContent=fa.length+" format"+(fa.length>1?"s":"");el("c3").textContent=fa.join(", ")+((D.sortie||{}).dossier?" · "+D.sortie.dossier:" · dossier de chaque recherche");}
      else el("c"+p).textContent=pretes+" prête"+(pretes>1?"s":"")+" sur "+tout.length+(p===2?" · "+(D.verification.mode==="plus"?"mode élargi":"mode recoupement"):"");
      if(p<3)dessinerAjouts(p);
      var fam=el("fam"+p);
      fam.innerHTML='<button class="'+(famSel[p]==="TOUT"?"on":"")+'" data-f="TOUT">tout</button>'+
        D.familles.map(function(f){
          var n=tout.filter(function(s){return s.famille===f}).length;
          return '<button class="'+(famSel[p]===f?"on":"")+(n?"":" vide")+'" data-f="'+esc(f)+'">'+esc(f)+(n?" "+n:"")+"</button>"}).join("");
      fam.querySelectorAll("button").forEach(function(b){b.onclick=function(){famSel[p]=b.dataset.f;rendre()}});
      var vis=tout.filter(function(s){return famSel[p]==="TOUT"||s.famille===famSel[p]});
      el("list"+p).innerHTML=vis.length?vis.map(function(s){return p===3?ligneFormat(s):ligneSource(s,p)}).join(""):'<div class="empty">Aucune source affichée. Utilise « Ajouter une source existante » ou « Ajouter une nouvelle source » ci-dessous.</div>';
      el("list"+p).querySelectorAll("input[type=checkbox][data-id]").forEach(function(inp){
        inp.onchange=function(){
          if(p===3){
            var ids=[].slice.call(el("list3").querySelectorAll("input[data-id]")).filter(function(x){return x.checked}).map(function(x){return x.dataset.id});
            file(function(){return envoyer("/api/reglages/sortie","PUT",{actifs:ids}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message);return charger()})});
          }else{
            var c={};c[p===1?"chercher":"verifier"]=inp.checked;envoyerSource(inp.dataset.id,c);
          }
        }});
      el("list"+p).querySelectorAll("button[data-retirer]").forEach(function(b){b.onclick=function(){
        var id=b.dataset.retirer;  /* visuel seulement : la source n'est pas supprimée, elle peut être remise par « Ajouter une source existante » */
        file(function(){return envoyer("/api/reglages/source/"+encodeURIComponent(id)+"/masquer","POST",{partie:PARTIE[p]}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message);return charger()})})}});
      el("list"+p).querySelectorAll("button[data-cout]").forEach(function(b){b.onclick=function(){
        var id=b.dataset.cout, corps={cout:{}}, champs=el("list"+p).querySelectorAll('input[data-id="'+id+'"][data-k]');
        [].slice.call(champs).forEach(function(i){
          if(i.dataset.k==="confiance")corps.confiance=parseFloat(i.value);
          else corps.cout[i.dataset.k]=i.dataset.k==="unite"?i.value:parseFloat(i.value)});
        envoyerSource(id,corps)}});
    });
    [1,2].forEach(function(p){
      var zone=el("list"+p);
      function msg(id,t){var m=zone.querySelector('[data-msg="'+id+'"]');if(m)m.textContent=t}
      zone.querySelectorAll("button[data-tester]").forEach(function(b){b.onclick=function(){
        msg(b.dataset.tester,"Test en cours…");
        envoyer("/api/sources/"+encodeURIComponent(b.dataset.tester)+"/tester","POST",{}).then(function(r){msg(b.dataset.tester,r.etat_phrase||"");return charger()}).catch(function(e){msg(b.dataset.tester,e.message)})}});
      zone.querySelectorAll("button[data-reel]").forEach(function(b){b.onclick=function(){
        var id=b.dataset.reel;
        api("/api/sources/"+encodeURIComponent(id)+"/test-reel").then(function(pr){
          var mot=window.prompt("Mot d'essai ?\n\nPrix de ce test : "+pr.phrase+(pr.avertissement?"\n\n"+pr.avertissement:""));if(!mot)return;
          if(!window.confirm("Lancer UNE vraie requête vers cette source ?\n"+pr.phrase))return;
          msg(id,"Requête en cours…");
          return envoyer("/api/sources/"+encodeURIComponent(id)+"/test-reel","POST",{mot:mot,confirme:true}).then(function(r){
            msg(id,r.total+" nom(s) rendu(s) : "+r.noms.map(function(n){return n.nom}).join(", ")+(r.dollars?" — dépensé : "+String(r.dollars).replace(".",",")+" $":""));return charger()})
        }).catch(function(e){msg(id,e.message)})}});
      zone.querySelectorAll("button[data-reprendre]").forEach(function(b){b.onclick=function(){
        envoyer("/api/sources/"+encodeURIComponent(b.dataset.reprendre)+"/reprendre","POST",{}).then(function(){return charger()}).catch(function(e){erreur(e.message)})}});
    });
    el("list3").querySelectorAll("input[data-fc]").forEach(function(i){i.onchange=function(){
      var contenus={};[].slice.call(el("list3").querySelectorAll("input[data-fc]")).forEach(function(x){if(x.checked)(contenus[x.dataset.fc]=contenus[x.dataset.fc]||[]).push(x.dataset.c)});
      (D.parties.sortie||[]).forEach(function(f){if(f.contenus.length>1&&!contenus[f.id])contenus[f.id]=null});
      Object.keys(contenus).forEach(function(k){if(contenus[k]===null)delete contenus[k]});
      file(function(){return envoyer("/api/reglages/sortie","PUT",{contenus:contenus}).then(function(){erreur("");return charger()}).catch(function(e){erreur(e.message);return charger()})})}});
    el("sortie-dossier").value=(D.sortie||{}).dossier||"";el("sortie-webhook").value=(D.sortie||{}).webhook_url||"";
    el("sortie-ok").onclick=function(){
      /* les valeurs sont lues AU CLIC, jamais dans la file : un redessin entre-temps remettrait les champs à ce que le serveur connaît */
      var corps={dossier:el("sortie-dossier").value,webhook_url:el("sortie-webhook").value};
      file(function(){return envoyer("/api/reglages/sortie","PUT",corps)
        .then(function(){el("sortie-msg").textContent="Enregistré.";erreur("")}).catch(function(e){el("sortie-msg").textContent="";erreur(e.message)})})};
    el("verif-sw").checked=D.verification.active;
    el("verif-txt").innerHTML=D.verification.active?TXT_ACTIF:TXT_COUPEE;
    /* Mode « plus » : appeler aussi les sources qui ne savent QUE vérifier (une capture d'archive, une liste de sanctions). */
    var seules=D.verification.verificatrices_seules||[];
    el("verif-mode-zone").style.display=D.verification.active&&seules.length?"flex":"none";
    el("verif-mode").checked=D.verification.mode==="plus";
    el("verif-mode-txt").innerHTML="Vérifier aussi avec les sources qui ne font que <b>vérifier</b> ("+esc(seules.join(", "))
      +") : elles sont appelées une fois par nom trouvé, après la recherche, et ajoutent une preuve sans changer le nombre d'endroits.";
  }

  function charger(){
    return api("/api/reglages").then(function(d){D=d;rendre()}).catch(function(e){erreur("Impossible de lire les réglages : "+e.message)});
  }
  el("verif-sw").onchange=function(){
    var sw=this, cible=sw.checked, mode=D.verification.mode;  /* lu au clic, pas dans la file */
    file(function(){return envoyer("/api/reglages/verification","PUT",{active:cible,mode:mode})
      .then(function(){D.verification.active=cible;rendre();erreur("")}).catch(function(e){sw.checked=!cible;erreur(e.message)})});
  };
  el("verif-mode").onchange=function(){
    var sw=this, mode=sw.checked?"plus":"memes", actif=D.verification.active;  /* lus au clic, pas dans la file */
    file(function(){return envoyer("/api/reglages/verification","PUT",{active:actif,mode:mode})
      .then(function(){erreur("");return charger()}).catch(function(e){sw.checked=mode!=="plus";erreur(e.message)})});
  };
  el("cat-voir").onclick=rendreCatalogue;
  el("budget-ok").onclick=function(){
    var v=parseFloat(el("budget-plafond").value);
    file(function(){return envoyer("/api/reglages/budget","PUT",{plafond_mensuel_usd:isNaN(v)?-1:v}).then(function(){erreur("");return charger()}).catch(function(e){erreur("Le plafond est refusé : "+e.message)})});
  };
  document.addEventListener("onglet",function(e){if(e.detail==="reglages")charger()});
  charger();
})();
