/* Assistant (fiche 02) : trois étapes — sources (bleu), vérification (violet), sortie (ambre) — puis un récapitulatif avec un bouton
   « Tester » par source. Il ne fait qu'ÉCRIRE les fichiers de configuration. Tant qu'il n'est pas terminé, le menu est caché. */
"use strict";
(function(){
  var D=null, S=null;
  function el(id){return document.getElementById(id)}
  function erreur(t){var e=el("as-erreur");e.style.display=t?"block":"none";e.textContent=t||""}
  function ids(ens){return Array.from(ens)}
  function sources(){return D.parties.recherche}
  function parId(id){return sources().find(function(s){return s.id===id})}
  /* une source couvre-t-elle le pays choisi ? (« monde » couvre tout ; sans pays choisi, tout est proposé) */
  function couvre(x,pays){return !pays||x.pays.indexOf("monde")>=0||x.pays.map(function(p){return p.toUpperCase()}).indexOf(pays.toUpperCase())>=0}

  /* ---------------- état initial ---------------- */
  function initialiser(mode,etape){
    var premiere=mode==="premiere";
    var coches=new Set(D.presets_coches);
    var chercher=new Set();
    sources().forEach(function(s){if(s.chercher&&!premiere)chercher.add(s.id)});
    if(premiere){D.presets.forEach(function(p){if(coches.has(p.id))p.sources.forEach(function(x){if(x.allumee_par_defaut)chercher.add(x.id)})})}
    var verifier=new Set();
    sources().forEach(function(s){if(s.verifier&&!premiere)verifier.add(s.id)});
    S={mode:mode,etape:etape,
       e1:{pays:D.pays||"",coches:coches,chercher:chercher,plafond:D.budget.plafond_mensuel_usd},
       e2:{active:D.verification.active,mode:D.verification.mode||"memes",verifier:verifier,initialise:!premiere}  /* le mode choisi dans Réglages est repris, jamais écrasé */,
       e3:{actifs:new Set(D.parties.sortie.filter(function(f){return f.actif}).map(function(f){return f.id})),dossier:""}};
  }

  /* ---------------- affichage des étapes ---------------- */
  function chips(){
    var noms=["① Sources","② Vérification","③ Sortie","④ Récapitulatif"];
    el("as-etapes").innerHTML=noms.map(function(n,i){
      if(S.mode!=="premiere"&&i+1!==S.etape)return "";
      // navette page 1 ↔ 4 (retour de Sednal, 02/11/2026) : en première installation, chaque étape reste cliquable pour y
      // aller directement plutôt que de cliquer plusieurs fois sur « Précédent »
      return '<span class="as-chip e'+(i+1)+(i+1===S.etape?" on":"")+'" data-aller="'+(i+1)+'" style="'+(S.mode==="premiere"?"cursor:pointer":"")+'">'+n+"</span>"}).join("");
    if(S.mode==="premiere")el("as-etapes").querySelectorAll("[data-aller]").forEach(function(c){c.onclick=function(){S.etape=+c.dataset.aller;montrer()}});
  }
  function montrer(){
    [1,2,3,4].forEach(function(n){el("as-e"+n).style.display=n===S.etape?"block":"none"});
    el("as-mode").textContent=S.mode==="premiere"?"· première installation":"· étape rejouée seule";
    el("as-prec").style.display=S.mode==="premiere"&&S.etape>1?"inline-block":"none";
    el("as-fermer").style.display=S.mode==="premiere"?"none":"inline-block";
    el("as-suiv").textContent=S.mode!=="premiere"?"Enregistrer et fermer":(S.etape===4?"Terminer et entrer dans le menu":"Suivant →");
    chips();erreur("");
    if(S.etape===1)etape1();else if(S.etape===2)etape2();else if(S.etape===3)etape3();else etape4();
  }

  /* ---------------- étape 1 ---------------- */
  function etape1(){
    var sel=el("as-pays"), pp=D.pays_proposes||{};
    var courant=S.e1.pays, autre=courant&&!pp[courant];
    sel.innerHTML='<option value="">— choisis —</option>'+Object.keys(pp).map(function(k){return '<option value="'+esc(k)+'"'+(k===courant?" selected":"")+">"+esc(pp[k])+"</option>"}).join("")+'<option value="__autre"'+(autre?" selected":"")+">Un autre pays…</option>";
    sel.value=autre?"__autre":courant;
    el("as-pays-autre-w").style.display=autre?"block":"none";if(autre)el("as-pays-autre").value=courant;
    sel.onchange=function(){if(sel.value==="__autre"){el("as-pays-autre-w").style.display="block";S.e1.pays=el("as-pays-autre").value.toUpperCase()}else{el("as-pays-autre-w").style.display="none";S.e1.pays=sel.value;etape1()}};
    el("as-pays-autre").oninput=function(){S.e1.pays=this.value.trim().toUpperCase()};
    el("as-presets").innerHTML=D.presets.map(function(p){
      var on=S.e1.coches.has(p.id);
      return '<div class="carte'+(on?" on":"")+'"><label style="display:flex;gap:8px;align-items:flex-start"><input type="checkbox" data-preset="'+esc(p.id)+'"'+(on?" checked":"")+' style="margin-top:3px">'
        +'<span><b>'+esc(p.nom)+"</b>"+(p.perso?' <span style="font:400 10.5px var(--mono);color:var(--faint)">· ajouté</span>':"")+'<br><span style="font-size:12.5px;color:var(--dim)">'+esc(p.phrase)+"</span></span></label>"
        +'<div style="margin:6px 0 0 24px;font-size:12px">'+(p.sources.length?p.sources.map(function(x){
          return '<label style="display:block"><input type="checkbox" data-src="'+esc(x.id)+'"'+(S.e1.chercher.has(x.id)?" checked":"")+"> "+esc(x.nom)
            +' <span style="color:var(--faint)">— '+(x.payant?"payant":"gratuit")+(x.cle_requise?(", clé "+(x.cle_presente?"présente":"absente")):"")+", "+esc(x.main==="premiere"?"première main":"seconde main")+", "+(x.pays.indexOf("monde")>=0?"monde entier":esc(x.pays.join(", ")))+(S.e1.pays&&x.pays.indexOf("monde")<0?(couvre(x,S.e1.pays)?" — couvre ton pays":" — ne couvre pas ton pays"):"")+"</span></label>"}).join(""):'<span style="color:var(--faint)">Aucune source pour l\'instant.</span>')+"</div>"
        +'<div style="margin:6px 0 0 24px;font-size:12px;color:var(--dim)">Coût : '+esc(p.cout)+' <button class="btn" data-perso="'+esc(p.id)+'" style="margin-left:8px;font-size:11.5px;padding:2px 8px">Personnaliser à partir de ce preset</button></div></div>'}).join("");
    el("as-presets").querySelectorAll("input[data-preset]").forEach(function(i){i.onchange=function(){
      var p=D.presets.find(function(x){return x.id===i.dataset.preset});
      if(i.checked){S.e1.coches.add(p.id);p.sources.forEach(function(x){if(x.allumee_par_defaut&&couvre(x,S.e1.pays))S.e1.chercher.add(x.id)})}
      else{S.e1.coches.delete(p.id);var gardees=new Set();D.presets.forEach(function(q){if(S.e1.coches.has(q.id))q.sources.forEach(function(x){gardees.add(x.id)})});
        p.sources.forEach(function(x){if(!gardees.has(x.id))S.e1.chercher.delete(x.id)})}
      etape1()}});
    el("as-presets").querySelectorAll("input[data-src]").forEach(function(i){i.onchange=function(){if(i.checked)S.e1.chercher.add(i.dataset.src);else S.e1.chercher.delete(i.dataset.src);etape1()}});
    el("as-presets").querySelectorAll("button[data-perso]").forEach(function(b){b.onclick=function(){
      var nom=window.prompt("Nom de ta copie modifiable de ce preset :");if(!nom)return;
      envoyer("/api/presets/personnaliser","POST",{depuis:b.dataset.perso,nom:nom}).then(function(){return recharger()}).then(function(){S.e1.coches.add(slugueur(nom));montrer()}).catch(function(e){erreur(e.message)})}});
    el("as-tout-selectionner").onclick=function(){
      D.presets.forEach(function(p){S.e1.coches.add(p.id);p.sources.forEach(function(x){S.e1.chercher.add(x.id)})});etape1()};
    el("as-tout-deselectionner").onclick=function(){S.e1.coches.clear();S.e1.chercher.clear();etape1()};
    // clés des sources choisies
    var besoin=ids(S.e1.chercher).map(parId).filter(function(s){return s&&s.cle_requise});
    el("as-cles").innerHTML=besoin.length?"<h3>Clés d’API</h3>"+besoin.map(function(s){
      return '<div class="maprow"><span class="lbl" style="width:170px">'+esc(s.nom)+'</span><span style="width:90px">'+(s.cle==="presente"?"<b>présente</b>":"absente")+"</span>"
        +'<input class="inp" type="password" autocomplete="off" data-cle-champ="'+esc(s.cle_nom)+'" placeholder="coller la clé" style="max-width:240px"> <button class="btn" data-cle="'+esc(s.cle_nom)+'">Enregistrer la clé</button></div>'}).join(""):"";
    el("as-cles").querySelectorAll("button[data-cle]").forEach(function(b){b.onclick=function(){
      var champ=el("as-cles").querySelector('input[data-cle-champ="'+b.dataset.cle+'"]');
      envoyer("/api/cles/"+encodeURIComponent(b.dataset.cle),"PUT",{valeur:champ.value}).then(function(){champ.value="";return recharger()}).then(montrer).catch(function(e){erreur(e.message)})}});
    // réglages requis des sources choisies (ex. adresse du portail CKAN) : ni une clé ni un coût, mais sans eux la
    // source reste rouge ; avant cet ajout, rien dans l'assistant ne permettait de les donner (02/11/2026)
    var besoinReglages=ids(S.e1.chercher).map(parId).filter(function(s){return s&&s.parametres_attendus&&Object.keys(s.parametres_attendus).length});
    el("as-reglages").innerHTML=besoinReglages.length?"<h3>Réglages requis</h3>"+besoinReglages.map(function(s){
      var attendus=s.parametres_attendus||{};
      return '<div class="maprow" style="flex-wrap:wrap"><span class="lbl" style="width:170px">'+esc(s.nom)+"</span>"
        +Object.keys(attendus).map(function(nom_p){
          var spec=attendus[nom_p]||{}, val=(s.parametres||{})[nom_p]||"";
          return '<span style="display:flex;align-items:center;gap:4px;margin-right:10px">'+esc(spec.libelle||nom_p)+(spec.requis?" *":"")
            +' <input class="inp" type="'+(spec.type==="url"?"url":"text")+'" data-reglage-champ="'+esc(nom_p)+'" data-reglage-id="'+esc(s.id)+'" value="'+esc(val)+'" style="max-width:220px"></span>'}).join("")
        +'<button class="btn" data-reglage-enreg="'+esc(s.id)+'">Enregistrer</button></div>'}).join(""):"";
    el("as-reglages").querySelectorAll("button[data-reglage-enreg]").forEach(function(b){b.onclick=function(){
      var id=b.dataset.reglageEnreg, champs=el("as-reglages").querySelectorAll('input[data-reglage-id="'+id+'"]'), parametres={};
      [].slice.call(champs).forEach(function(i){parametres[i.dataset.reglageChamp]=i.value});
      envoyer("/api/reglages/source/"+encodeURIComponent(id),"PUT",{parametres:parametres}).then(function(){return recharger()}).then(montrer).catch(function(e){erreur(e.message)})}});
    var payant=ids(S.e1.chercher).map(parId).some(function(s){return s&&s.payant});
    el("as-plafond-w").style.display=payant?"block":"none";el("as-plafond").value=S.e1.plafond;el("as-plafond").oninput=function(){S.e1.plafond=parseFloat(this.value)};
  }
  function slugueur(nom){return nom.normalize("NFKD").replace(/[̀-ͯ]/g,"").toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,48)}

  /* ---------------- étape 2 ---------------- */
  function etape2(){
    var sw=el("as-verif");sw.checked=S.e2.active;
    el("as-verif-txt").textContent=S.e2.active?"Vérification activée.":"Vérification désactivée : le résultat sort brut, sans confirmation.";
    sw.onchange=function(){S.e2.active=sw.checked;etape2()};
    el("as-verif-detail").style.display=S.e2.active?"block":"none";
    document.querySelectorAll('input[name="as-mode-verif"]').forEach(function(r){r.checked=r.value===S.e2.mode;r.onchange=function(){S.e2.mode=r.value;etape2()}});
    var capables=sources().filter(function(s){return s.roles.indexOf("verifier")>=0});
    var eligibles=S.e2.mode==="memes"?capables.filter(function(s){return S.e1.chercher.has(s.id)}):capables;
    if(!S.e2.initialise){eligibles.forEach(function(s){if(s.defaut.verifier||S.e2.mode==="memes")S.e2.verifier.add(s.id)});S.e2.initialise=true}
    el("as-verif-sources").innerHTML=eligibles.length?eligibles.map(function(s){
      return '<label style="display:block;font-size:12.5px;margin:3px 0"><input type="checkbox" data-ver="'+esc(s.id)+'"'+(S.e2.verifier.has(s.id)?" checked":"")+"> Utiliser <b>"+esc(s.nom)+"</b> pour vérifier <span style=\"color:var(--faint)\">— "+esc(s.main_phrase)+"</span></label>"}).join(""):'<span style="color:var(--faint)">Aucune source ne peut vérifier avec ce choix.</span>';
    el("as-verif-sources").querySelectorAll("input").forEach(function(i){i.onchange=function(){if(i.checked)S.e2.verifier.add(i.dataset.ver);else S.e2.verifier.delete(i.dataset.ver)}});
  }

  /* ---------------- étape 3 ---------------- */
  function etape3(){
    el("as-formats").innerHTML=D.parties.sortie.map(function(f){
      return '<label style="display:block;font-size:12.5px;margin:3px 0"><input type="checkbox" data-fmt="'+esc(f.id)+'"'+(S.e3.actifs.has(f.id)?" checked":"")+"> <b>"+esc(f.nom)+'</b> <span style="color:var(--faint)">— '+esc(f.description)+"</span></label>"}).join("");
    el("as-formats").querySelectorAll("input").forEach(function(i){i.onchange=function(){if(i.checked)S.e3.actifs.add(i.dataset.fmt);else S.e3.actifs.delete(i.dataset.fmt)}});
    el("as-dossier").value=S.e3.dossier;el("as-dossier").oninput=function(){S.e3.dossier=this.value};
  }

  /* ---------------- étape 4 : récapitulatif ---------------- */
  function dotCible(id){return el("as-dot-"+id)}
  function testerUne(id){
    var cible=el("as-etat-"+id), dot=dotCible(id);dot.className="dot warn";cible.textContent="Test en cours…";
    return envoyer("/api/sources/"+encodeURIComponent(id)+"/tester","POST",{}).then(function(r){
      cible.textContent=(r.statut==="ok"?"✓ ":"✕ ")+(r.statut==="ok"?"":r.raison+" — ")+r.etat_phrase;
      dot.className="dot "+(r.statut==="ok"?"ok":"err");return r.statut==="ok"
    }).catch(function(e){cible.textContent="✕ "+e.message;dot.className="dot err";return false});
  }
  function etape4(){
    var chois=sources().filter(function(s){return S.e1.chercher.has(s.id)||(S.e2.active&&S.e2.verifier.has(s.id))});
    el("as-recap").innerHTML=chois.length?chois.map(function(s){
      var roles=[S.e1.chercher.has(s.id)?"cherche":"",S.e2.active&&S.e2.verifier.has(s.id)?"vérifie":""].filter(Boolean).join(" et ");
      var dc=(s.voyant&&s.voyant[0])||"off";
      return '<div class="srow" style="align-items:flex-start"><span class="dot '+esc(dc)+'" id="as-dot-'+esc(s.id)+'" title="'+esc((s.voyant&&s.voyant[1])||"")+'" style="margin-top:4px"></span><span class="sgrow"><span class="sname">'+esc(s.nom)+'</span><span class="smeta" style="white-space:normal">'+roles+" — "+esc(s.main_phrase)
        +(s.cle_requise?" — clé "+(s.cle==="presente"?"présente":"absente"):"")+'</span><span class="smeta" style="white-space:normal" id="as-etat-'+esc(s.id)+'">'+esc(s.etat_phrase)+"</span></span>"
        +'<button class="btn" data-tester="'+esc(s.id)+'">Tester</button></div>'}).join(""):'<div class="empty">Aucune source choisie : retourne à l\'étape 1.</div>';
    el("as-recap").querySelectorAll("button[data-tester]").forEach(function(b){b.onclick=function(){
      b.disabled=true;testerUne(b.dataset.tester).then(function(){b.disabled=false})}});
    var btnTout=el("as-tester-tout"), etatTout=el("as-tester-tout-etat"), btnSansCle=el("as-decocher-sans-cle");
    var sansCle=chois.filter(function(s){return s.cle_requise&&s.cle!=="presente"});
    btnTout.style.display=chois.length?"inline-block":"none";
    btnSansCle.style.display=sansCle.length?"inline-block":"none";
    btnSansCle.textContent="Décocher les sources sans clé ("+sansCle.length+")";
    el("as-retour-sources").style.display=S.mode==="premiere"?"inline-block":"none";
    btnSansCle.onclick=function(){
      sansCle.forEach(function(s){S.e1.chercher.delete(s.id);S.e2.verifier.delete(s.id)});
      etape4();
    };
    el("as-retour-sources").onclick=function(){S.etape=1;montrer()};
    btnTout.onclick=function(){
      btnTout.disabled=true;el("as-recap").querySelectorAll("button[data-tester]").forEach(function(b){b.disabled=true});
      var i=0, ok=0;
      function suivante(){
        if(i>=chois.length){
          etatTout.textContent=ok+" / "+chois.length+" vérifiées sans problème.";
          btnTout.disabled=false;el("as-recap").querySelectorAll("button[data-tester]").forEach(function(b){b.disabled=false});
          return;
        }
        var s=chois[i++];etatTout.textContent="Test "+i+" / "+chois.length+" — "+s.nom+"…";
        testerUne(s.id).then(function(reussi){if(reussi)ok++;suivante()});
      }
      suivante();
    };
  }

  /* ---------------- envoi ---------------- */
  function donnees(n){
    if(n===1)return {pays:S.e1.pays,presets_coches:ids(S.e1.coches),chercher:ids(S.e1.chercher),plafond:isNaN(S.e1.plafond)?undefined:S.e1.plafond};
    if(n===2)return {active:S.e2.active,mode:S.e2.mode,verifier:ids(S.e2.verifier)};
    return {actifs:ids(S.e3.actifs),dossier:S.e3.dossier};
  }
  el("as-suiv").onclick=function(){
    if(S.mode!=="premiere"){
      envoyerConfirme("/api/assistant/etape/"+S.etape,"POST",{donnees:donnees(S.etape)}).then(function(){location.reload()}).catch(function(e){erreur(e.message)});return;
    }
    if(S.etape<4){S.etape++;montrer();return}
    envoyerConfirme("/api/assistant/terminer","POST",{etape1:donnees(1),etape2:donnees(2),etape3:donnees(3)}).then(function(){location.reload()}).catch(function(e){erreur(e.message)});
  };
  el("as-prec").onclick=function(){if(S.etape>1){S.etape--;montrer()}};
  el("as-fermer").onclick=function(){fermer()};
  function fermer(){el("assistant").style.display="none"}

  function recharger(){return api("/api/reglages").then(function(d){D=d})}
  function ouvrir(mode,etape){
    return recharger().then(function(){initialiser(mode,etape);el("assistant").style.display="block";
      if(mode==="premiere")document.body.classList.add("sans-menu");montrer()});
  }
  document.querySelectorAll("button[data-rouvrir]").forEach(function(b){b.onclick=function(){ouvrir("etape",+b.dataset.rouvrir)}});
  api("/api/reglages").then(function(d){D=d;if(d.assistant.premiere_installation)ouvrir("premiere",1)}).catch(function(){});
})();
