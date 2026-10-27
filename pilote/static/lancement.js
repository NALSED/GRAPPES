/* Page Recherches : sujet en champs séparés, presets, estimation, options avancées, lancement immédiat / daté / récurrent, suivi en direct.
   Aucun résultat ici : les noms se trouvent dans Tri. */
"use strict";
(function(){
  var OPTIONS=null, depthSel=null, courante=localStorageLire("g_recherche"), minuteur=null, progType=null;
  var ETAT_FIN={terminee:true,arretee:true,echec:true,interrompue:true};
  var TITRE_ETAT={en_attente:"En attente de démarrage",en_cours:"En cours",terminee:"Terminée",arretee:"Arrêtée — ce qui a été trouvé est gardé",echec:"S'est arrêtée sur une panne",interrompue:"Interrompue — ce qui a été trouvé est gardé"};
  var JOURS=["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"];

  function localStorageLire(k){try{return localStorage.getItem(k)}catch(e){return null}}
  function localStorageEcrire(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  function el(id){return document.getElementById(id)}
  function erreur(msg){var e=el("lancement-erreur");e.style.display=msg?"block":"none";e.textContent=msg||""}

  /* ---- champs « puces » (mots à inclure, à exclure, exemples) ---- */
  var puces={inc:[],exc:[],amo:[],ign:[]};
  ["inc","exc","amo","ign"].forEach(function(z){
    var box=el(z), inp=box.querySelector("input");
    function ajouter(t){
      var s=document.createElement("span");s.className="chip"+(z==="exc"?" ex":"");
      s.appendChild(document.createTextNode(t+" "));
      var x=document.createElement("span");x.className="x";x.textContent="×";
      x.onclick=function(){s.remove();puces[z]=puces[z].filter(function(m){return m!==t});estimer()};
      s.appendChild(x);box.insertBefore(s,inp);puces[z].push(t);estimer();
    }
    inp.onkeydown=function(e){if(e.key==="Enter"&&inp.value.trim()){ajouter(inp.value.trim());inp.value="";e.preventDefault()}};
    inp.onblur=function(){if(inp.value.trim()){ajouter(inp.value.trim());inp.value=""}};
  });

  /* ---- profondeur ---- */
  function rendreProfondeur(){
    el("depth").innerHTML=OPTIONS.profondeurs.map(function(d){
      return '<button class="'+(d.id===depthSel?"on":"")+'" data-id="'+esc(d.id)+'"><span class="dn">'+esc(d.nom)+'</span>'
        +'<span class="dd">'+esc(d.description)+'</span><span class="dc">jusqu\'à '+d.appels+' appels</span></button>'}).join("");
    el("depth").querySelectorAll("button").forEach(function(b){b.onclick=function(){depthSel=b.dataset.id;rendreProfondeur()}});
  }

  /* ---- lancement ---- */
  function cochees(zone){return [].slice.call(el(zone).querySelectorAll("input[type=checkbox]")).filter(function(x){return x.checked}).map(function(x){return x.dataset.id})}
  function parametresFormulaire(){
    var appels=parseInt(el("f-appels").value,10), temps=parseInt(el("f-temps").value,10), v=el("f-verif").value;
    var p={profondeur:depthSel,limites:{temps_minutes:temps||null,appels:appels||null},verification:v==="oui"?true:v==="non"?false:null,
           presets:cochees("f-presets"),exploration:parseInt(el("f-explo").value,10)||0};
    if(el("f-page").value==="extrait")p.lire_la_page=false;
    if(el("f-regle8").checked)p.regle8_afficher_comptes=true;
    if(el("f-typelieu").value)p.type_lieu=[el("f-typelieu").value];
    if(puces.ign.length)p.sites_a_ignorer=puces.ign.slice();
    var so=cochees("f-sortie");if(so.length)p.sortie={actifs:so};
    return p;
  }
  function lireFormulaire(){
    var quoi=el("f-quoi").value.trim();
    if(!quoi)throw new Error("Dites d'abord ce que vous cherchez.");
    return {
      sujet:{quoi:quoi,genre:el("f-genre").value,langue:el("f-langue").value,pays:el("f-pays").value.trim(),lieu:el("f-lieu").value.trim(),
             inclure:puces.inc.slice(),exclure:puces.exc.slice(),exemples:puces.amo.slice(),periode:el("f-periode").value,combien:parseInt(el("f-combien").value,10)||50},
      parametres:parametresFormulaire()
    };
  }

  /* ---- fourchette de temps et de coût, avant le lancement ---- */
  var delaiEst=null;
  function estimer(){
    if(delaiEst)clearTimeout(delaiEst);
    delaiEst=setTimeout(function(){
      envoyer("/api/lancement/estimation","POST",{sujet:{pays:el("f-pays").value.trim()},parametres:parametresFormulaire()}).then(function(e){
        el("est-temps").textContent="Temps estimé : "+e.temps.phrase;
        el("est-cout").textContent="Coût estimé : "+e.cout.phrase;
        el("est-plafond").textContent="Plafond du mois : "+e.plafond.mensuel_usd.toFixed(2).replace(".",",")+" $ — dépensé "+e.plafond.depense_usd.toFixed(2).replace(".",",")+" $";
        el("est-message").textContent=e.message||"";
        el("est-copies").innerHTML=(e.copies_locales||[]).map(function(x){return "<div>"+esc(x)+"</div>"}).join("");
      }).catch(function(x){el("est-message").textContent=x.message});
    },250);
  }
  ["f-appels","f-temps","f-explo","f-page","f-verif","f-typelieu","f-pays"].forEach(function(id){el(id).onchange=estimer;el(id).oninput=estimer});

  /* ---- presets cochés, formats de sortie, types de lieu ---- */
  function chargerChoix(){
    api("/api/reglages").then(function(d){
      var coches=d.presets_coches||[];
      el("f-presets").innerHTML=d.presets.map(function(p){
        return '<label style="display:inline-block;margin:0 14px 4px 0"><input type="checkbox" data-id="'+esc(p.id)+'"'+(coches.indexOf(p.id)>=0?" checked":"")+"> "+esc(p.nom)+"</label>"}).join("");
      el("f-presets").querySelectorAll("input").forEach(function(i){i.onchange=estimer});
      var actifs=((d.parties||{}).sortie||[]);
      el("f-sortie").innerHTML=actifs.length?actifs.map(function(f){
        return '<label style="display:inline-block;margin:0 14px 4px 0"><input type="checkbox" data-id="'+esc(f.id)+'"'+(f.actif?" checked":"")+"> "+esc(f.nom)+"</label>"}).join("")+'<div class="smeta">Décoché partout = comme dans Réglages.</div>':"";
      estimer();
    }).catch(function(){});
    api("/api/types-de-lieu").then(function(t){
      el("f-typelieu").innerHTML='<option value="">tous</option>'+t.types.map(function(x){return '<option value="'+esc(x.id)+'">'+esc(x.libelle)+"</option>"}).join("");
    }).catch(function(){});
  }

  function lancerMaintenant(){
    var f;try{f=lireFormulaire()}catch(e){erreur(e.message);return}
    el("go").disabled=true;erreur("");
    envoyer("/api/recherches","POST",f).then(function(r){
      courante=r.id;localStorageEcrire("g_recherche",courante);suivre();charger_listes();
    }).catch(function(e){erreur("Le lancement n'a pas pu se faire : "+e.message)}).then(function(){el("go").disabled=false});
  }
  el("go").onclick=lancerMaintenant;

  function ouvrirProg(type){
    progType=type;el("prog").style.display="block";
    el("prog-date-w").style.display=type==="date"?"block":"none";
    el("prog-jours-w").style.display=type==="rec"?"block":"none";
    el("prog-heure-w").style.display=type==="rec"?"block":"none";
    if(type==="date"&&!el("prog-date").value){var d=new Date(Date.now()+3600e3);d.setMinutes(0,0,0);
      el("prog-date").value=new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
  }
  el("go-date").onclick=function(){ouvrirProg("date")};
  el("go-rec").onclick=function(){ouvrirProg("rec")};
  el("prog-non").onclick=function(){el("prog").style.display="none"};
  el("prog-ok").onclick=function(){
    var f;try{f=lireFormulaire()}catch(e){erreur(e.message);return}
    var quand;
    if(progType==="date"){if(!el("prog-date").value){erreur("Choisissez une date.");return}quand={date:el("prog-date").value}}
    else{var j=el("prog-jours").value;quand={jours:j==="tous"?[]:[parseInt(j,10)],heure:el("prog-heure").value||"10:00"}}
    envoyer("/api/programmes","POST",{sujet:f.sujet,parametres:f.parametres,quand:quand}).then(function(){
      erreur("");el("prog").style.display="none";charger_listes()}).catch(function(e){erreur("La programmation n'a pas pu se faire : "+e.message)});
  };

  /* ---- suivi en direct ---- */
  function gauges(r){
    var a=r.avancement||{}, etape=a.etape||"recherche", prises=a.prises||{}, out=[];
    Object.keys(prises).forEach(function(nom){
      var p=prises[nom], f=p.fini?1:(p.prevus?Math.min(1,p.faits/p.prevus):0);
      out.push({n:nom,s:1,f:f,v:p.fini?(p.trouves+" noms"):(p.faits+" appel"+(p.faits>1?"s":""))});
    });
    if(!out.length)out.push({n:"Sources",s:1,f:etape==="recherche"?0.1:1,v:etape==="recherche"?"en cours":"fait"});
    var iv=etape==="verification"?0.5:(etape==="sortie"||etape==="fini")?1:0;
    out.push({n:"Recoupement et vérification",s:2,f:iv,v:iv===1?"fait":iv?"en cours":"à venir"});
    var is=etape==="sortie"?0.5:etape==="fini"?1:0;
    out.push({n:"Écriture",s:3,f:is,v:is===1?"fait":is?"en cours":"à venir"});
    return out;
  }
  function fourchette(r){
    var a=r.avancement||{};
    if(ETAT_FIN[r.etat])return r.etat==="terminee"?"terminé":"fini";
    if(!a.appels_faits||!a.appels_prevus||a.appels_faits>=a.appels_prevus||!a.secondes)return "—";
    var reste=a.secondes*(a.appels_prevus-a.appels_faits)/a.appels_faits;
    if(reste<60)return "moins d'une minute";
    return "entre "+Math.max(1,Math.floor(reste*0.7/60))+" et "+Math.ceil(reste*1.5/60)+" min";
  }
  function bilanHtml(a){
    var h=[];
    if(a.en_pause)h.push("<div><b>En pause</b> — elle reprend au prochain point d'arrêt de la collecte quand vous cliquez sur « Reprendre ».</div>");
    if(a.sources_ecartees&&a.sources_ecartees.length)h.push("<div><b>"+(a.limitee_aux_gratuites?"Limitée aux sources gratuites":"Sources payantes écartées")+"</b> : le plafond de dépense du mois écarte "+a.sources_ecartees.map(function(x){return esc(x.nom||x.source)}).join(", ")+".</div>");
    if(a.sources_en_pause&&a.sources_en_pause.length)h.push("<div>"+a.sources_en_pause.map(function(x){return esc(x.nom||x.source)+" en pause : "+esc(x.raison)}).join(" ; ")+" (à remettre en service dans Réglages).</div>");
    if(a.sources_bilan){
      h.push("<div><b>"+esc(a.sources_bilan.phrase)+"</b>"+(a.sources_bilan.echecs.length?" — en échec : "+a.sources_bilan.echecs.map(function(x){return esc(x.nom)+" ("+esc(x.raison)+")"}).join(" ; "):"")+"</div>");
      (a.sources_bilan.nouvelles_pauses||[]).forEach(function(p){h.push("<div>"+esc(p.nom)+" en pause : "+esc(p.raison)+".</div>")});
    }
    return h.join("");
  }
  function dessiner(r){
    el("rien-en-cours").style.display="none";el("en-cours").style.display="block";
    var a=r.avancement||{};
    el("rtitre").textContent=(r.sujet&&r.sujet.quoi?r.sujet.quoi+" — ":"")+(TITRE_ETAT[r.etat]||r.etat);
    el("rn").textContent=a.noms||0;
    el("rcalls").textContent=(a.appels_faits||0)+" / "+(a.appels_prevus||0)+" appels";
    el("reta").textContent=fourchette(r);
    el("gauges").innerHTML=gauges(r).map(function(g){
      return '<div class="g s'+g.s+'"><span class="gn">'+esc(g.n)+'</span><span class="gb"><span class="gf" style="width:'+Math.round(g.f*100)+'%"></span></span><span class="gv">'+esc(g.v)+"</span></div>"}).join("");
    var fini=!!ETAT_FIN[r.etat];
    el("stop").style.display=fini?"none":"inline-block";
    el("pause").style.display=fini||r.etat!=="en_cours"?"none":"inline-block";
    el("pause").textContent=a.en_pause?"Reprendre":"Mettre en pause";
    el("bilan").innerHTML=bilanHtml(a);
    el("voir-tri").style.display=fini&&(a.noms||0)>0?"inline-block":"none";
    var msg=r.message||"";
    if(a.arret==="temps")msg="La limite de temps a été atteinte ; ce qui était trouvé est gardé.";
    else if(a.arret==="appels")msg="La limite d'appels a été atteinte ; ce qui était trouvé est gardé.";
    el("rmsg").textContent=fini?msg:"";
    if(window.chargerContexte&&(fini||(a.noms||0)>0))window.chargerContexte(r.id,fini?"fin":"cours");  // les titres déjà collectés (aucune nouvelle collecte)
  }
  function suivre(){
    if(minuteur){clearInterval(minuteur);minuteur=null}
    if(!courante)return;
    function tour(){
      api("/api/recherches/"+courante).then(function(r){
        dessiner(r);
        if(ETAT_FIN[r.etat]){clearInterval(minuteur);minuteur=null;charger_listes()}
      }).catch(function(){clearInterval(minuteur);minuteur=null});
    }
    tour();minuteur=setInterval(tour,1500);
  }
  el("stop").onclick=function(){
    if(!courante)return;
    el("stop").disabled=true;
    envoyer("/api/recherches/"+courante+"/arret","POST",{}).catch(function(e){erreur("L'arrêt n'a pas pu être demandé : "+e.message)}).then(function(){el("stop").disabled=false});
  };
  el("pause").onclick=function(){
    if(!courante)return;
    el("pause").disabled=true;
    var reprendre=el("pause").textContent==="Reprendre";
    envoyer("/api/recherches/"+courante+(reprendre?"/reprise":"/pause"),"POST",{}).catch(function(e){erreur("La pause n'a pas pu être changée : "+e.message)}).then(function(){el("pause").disabled=false});
  };
  el("voir-tri").onclick=function(){var t=document.querySelector('.tab[data-p="tri"]');if(t)t.click()};

  /* ---- listes : programmées, dernières recherches ---- */
  function charger_listes(){
    api("/api/programmes").then(function(ps){
      el("programmees").innerHTML=ps.length?ps.map(function(p){
        var suiv=p.prochaine?new Date(p.prochaine).toLocaleString("fr-FR",{weekday:"short",day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"}):"";
        return '<div class="r"><label class="sw"><input type="checkbox" data-id="'+esc(p.id)+'"'+(p.actif?" checked":"")+'><i></i><b></b></label>'
          +'<span class="sgrow">'+esc(p.libelle)+'</span><span class="num" style="color:var(--dim);font-size:11.5px">'+(p.actif?esc(suiv):"suspendue")+"</span></div>"}).join("")
        :'<div class="r"><span class="sgrow" style="color:var(--faint)">Rien de programmé.</span></div>';
      el("programmees").querySelectorAll("input").forEach(function(inp){
        inp.onchange=function(){envoyer("/api/programmes/"+inp.dataset.id,"PUT",{actif:inp.checked}).then(charger_listes).catch(function(e){erreur(e.message);charger_listes()})}});
    }).catch(function(){});
    api("/api/recherches").then(function(rs){
      var dern=rs.filter(function(r){return ETAT_FIN[r.etat]}).slice(0,6);
      el("dernieres").innerHTML=dern.length?dern.map(function(r){
        return '<div class="r"><span class="sgrow">'+esc((r.sujet&&r.sujet.quoi)||"(sans titre)")+'</span><span class="num" style="font-size:11.5px;color:var(--dim)">'
          +r.noms.toLocaleString("fr-FR")+" · "+r.tries.toLocaleString("fr-FR")+" trié"+(r.tries>1?"s":"")+"</span></div>"}).join("")
        :'<div class="r"><span class="sgrow" style="color:var(--faint)">Aucune recherche pour l\'instant.</span></div>';
      var encours=rs.find(function(r){return !ETAT_FIN[r.etat]});
      if(encours&&encours.id!==courante){courante=encours.id;localStorageEcrire("g_recherche",courante);suivre()}
    }).catch(function(){});
  }

  api("/api/lancement/options").then(function(o){
    OPTIONS=o;depthSel=o.profondeur_par_defaut;rendreProfondeur();
    if(o.limites_par_defaut&&o.limites_par_defaut.temps_minutes)el("f-temps").value=o.limites_par_defaut.temps_minutes;
  }).catch(function(e){erreur("Impossible de lire les options : "+e.message)});
  charger_listes();suivre();chargerChoix();
  document.addEventListener("onglet",function(e){if(e.detail==="lancement"){charger_listes();chargerChoix()}});
})();
