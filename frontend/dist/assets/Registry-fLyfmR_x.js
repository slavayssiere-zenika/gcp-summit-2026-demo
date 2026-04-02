import{c as _,d as x,o as b,b as a,e as s,f as u,u as d,t as o,h as q,F as v,m,g as w,r as p,l as t,p as N,j as y,_ as R}from"./index-4vmwmnCj.js";import{D as z,C as B}from"./database-BoyjoM3F.js";import{C as I}from"./chevron-right-CNsTxwXY.js";/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=_("ActivityIcon",[["path",{d:"M22 12h-4l-3 9L9 3l-3 9H2",key:"d5dnw9"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=_("BoxIcon",[["path",{d:"M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",key:"hh9hay"}],["path",{d:"m3.3 7 8.7 5 8.7-5",key:"g66t2b"}],["path",{d:"M12 22V12",key:"d0xqtd"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=_("Code2Icon",[["path",{d:"m18 16 4-4-4-4",key:"1inbqp"}],["path",{d:"m6 8-4 4 4 4",key:"15zrgr"}],["path",{d:"m14.5 4-5 16",key:"e7oirm"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=_("TerminalIcon",[["polyline",{points:"4 17 10 11 4 5",key:"akl6gq"}],["line",{x1:"12",x2:"20",y1:"19",y2:"19",key:"q2wloq"}]]),M={class:"registry-container"},A={class:"registry-header"},j={class:"stats-bar"},E={class:"stat-item"},L={class:"stat-item"},$={key:0,class:"loading-state"},F={key:1,class:"error-state"},H={key:2,class:"registry-layout"},J={class:"registry-sidebar"},O=["onClick"],P={class:"nav-icon"},Y={class:"nav-info"},Z={class:"nav-name"},G={class:"nav-count"},K={key:0,class:"registry-main"},Q={class:"tools-grid"},U={class:"tool-card-header"},W={class:"tool-type-icon"},X={class:"tool-desc"},ss={class:"params-section"},es={class:"params-table"},ts={class:"code-text"},as={class:"type-text"},ns={class:"status-cell"},os={key:0,class:"required-badge"},is={key:1,class:"optional-badge"},ls={class:"code-text dimmed"},rs={class:"technical-snippet"},ds=x({__name:"Registry",setup(cs){const l=p([]),g=p(!0),h=p(null),c=p(null),k=async()=>{try{const r=await fetch("/api/mcp/registry");if(!r.ok)throw new Error("Erreur lors du chargement du registre");const n=await r.json();l.value=n.services,l.value.length>0&&(c.value=l.value[0].id)}catch(r){h.value=r.message}finally{g.value=!1}};b(k);const f=()=>l.value.find(r=>r.id===c.value);return(r,n)=>{var C;return t(),a("div",M,[s("header",A,[n[0]||(n[0]=s("div",{class:"title-group"},[s("h1",null,"MCP Technical Registry"),s("p",null,"Vue consolidée des descripteurs techniques de tous les microservices intégrés.")],-1)),s("div",j,[s("div",E,[u(d(S),{size:"18"}),s("span",null,o(l.value.length)+" Services",1)]),s("div",L,[u(d(V),{size:"18"}),s("span",null,o(l.value.reduce((e,i)=>e+i.tools.length,0))+" Tools",1)])])]),g.value?(t(),a("div",$,[...n[1]||(n[1]=[s("div",{class:"spinner"},null,-1),q(" Chargement du registre technique... ",-1)])])):h.value?(t(),a("div",F,[s("p",null,o(h.value),1),s("button",{onClick:k},"Réessayer")])):(t(),a("div",H,[s("aside",J,[(t(!0),a(v,null,m(l.value,e=>(t(),a("div",{key:e.id,class:N(["service-nav-item",{active:c.value===e.id}]),onClick:i=>c.value=e.id},[s("div",P,[e.id==="users"?(t(),y(d(z),{key:0})):e.id==="items"?(t(),y(d(T),{key:1})):(t(),y(d(B),{key:2}))]),s("div",Y,[s("span",Z,o(e.name),1),s("span",G,o(e.tools.length)+" endpoints",1)]),u(d(I),{class:"nav-arrow",size:"16"})],10,O))),128))]),f()?(t(),a("main",K,[s("div",Q,[(t(!0),a(v,null,m((C=f())==null?void 0:C.tools,e=>(t(),a("div",{key:e.name,class:"tool-card"},[s("div",U,[s("div",W,[u(d(D),{size:"16"})]),s("h3",null,o(e.name),1)]),s("p",X,o(e.description),1),s("div",ss,[n[3]||(n[3]=s("div",{class:"params-header"},"Descripteur d'arguments :",-1)),s("div",es,[n[2]||(n[2]=s("div",{class:"param-row header"},[s("span",null,"Nom"),s("span",null,"Type"),s("span",null,"Requis"),s("span",null,"Défaut")],-1)),(t(!0),a(v,null,m(e.parameters,i=>(t(),a("div",{key:i.name,class:"param-row"},[s("span",ts,o(i.name),1),s("span",as,o(i.type),1),s("span",ns,[i.required?(t(),a("span",os,"Yes")):(t(),a("span",is,"No"))]),s("span",ls,o(i.default||"-"),1)]))),128))])]),s("div",rs,[n[4]||(n[4]=s("div",{class:"snippet-header"},"JSON Spec",-1)),s("pre",null,[s("code",null,`{
  "method": "`+o(e.name)+`",
  "params": {
    `+o(e.parameters.map(i=>`"${i.name}": "${i.type}"`).join(`,
    `))+`
  }
}`,1)])])]))),128))])])):w("",!0)]))])}}}),hs=R(ds,[["__scopeId","data-v-3d945694"]]);export{hs as default};
