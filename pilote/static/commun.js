/* Éléments communs : onglets (mémorisés), échappement du texte venu de la configuration, appels à l'API. */
"use strict";
function esc(t){return String(t==null?"":t).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
async function api(chemin,options){
  var r=await fetch(chemin,options);
  if(!r.ok){
    var m="",av=null;
    try{var d=(await r.json()).detail;if(d&&typeof d==="object"&&!Array.isArray(d)){av=d.avertissements||null;m="Confirmation demandée."}else m=d}catch(e){}
    var er=new Error(m||("Erreur "+r.status));er.avertissements=av;throw er;
  }
  return r.json();
}
function envoyer(chemin,methode,corps){
  return api(chemin,{method:methode,headers:{"content-type":"application/json"},body:JSON.stringify(corps)});
}
/* Avertissement d'une source (prestataire payant, service à risque) : montré UNE fois, à l'activation. Si le serveur le demande,
   on l'affiche en toutes lettres ; sur « OK » on renvoie la même demande avec « confirme » ; sur « Annuler » rien n'est écrit. */
function envoyerConfirme(chemin,methode,corps){
  return envoyer(chemin,methode,corps).catch(function(e){
    if(!e.avertissements)throw e;
    var texte=e.avertissements.map(function(a){return a.nom+" : "+a.texte}).join("\n\n");
    if(!window.confirm("Avant d’activer :\n\n"+texte+"\n\nActiver quand même ?"))throw new Error("Activation annulée.");
    return envoyer(chemin,methode,Object.assign({},corps,{confirme:true}));
  });
}
document.getElementById("adresse").textContent=location.origin;
document.querySelectorAll(".tab").forEach(function(t){
  t.addEventListener("click",function(){
    document.querySelectorAll(".tab").forEach(function(x){x.setAttribute("aria-selected","false")});
    t.setAttribute("aria-selected","true");
    document.querySelectorAll(".page").forEach(function(p){p.classList.remove("on")});
    document.getElementById("pg-"+t.dataset.p).classList.add("on");
    try{localStorage.setItem("g_tab",t.dataset.p)}catch(e){}
    document.dispatchEvent(new CustomEvent("onglet",{detail:t.dataset.p}));
  });
});
try{var sv=localStorage.getItem("g_tab");if(sv){var b=document.querySelector('.tab[data-p="'+sv+'"]');if(b)b.click()}}catch(e){}
