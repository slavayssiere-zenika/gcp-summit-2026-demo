import{c as v,d as b,o as x,b as n,e as s,f as p,u as l,t as o,h as q,F as y,m as g,g as N,r as _,q as R,l as t,p as z,j as h,C as B,_ as I}from"./index-DY2FiiYI.js";import{D as M,C as S}from"./database-DG99iUif.js";import{T}from"./terminal-C7u7xr9G.js";/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=v("ActivityIcon",[["path",{d:"M22 12h-4l-3 9L9 3l-3 9H2",key:"d5dnw9"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const w=v("BoxIcon",[["path",{d:"M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",key:"hh9hay"}],["path",{d:"m3.3 7 8.7 5 8.7-5",key:"g66t2b"}],["path",{d:"M12 22V12",key:"d0xqtd"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=v("CloudIcon",[["path",{d:"M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z",key:"p7xjir"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const A=v("Code2Icon",[["path",{d:"m18 16 4-4-4-4",key:"1inbqp"}],["path",{d:"m6 8-4 4 4 4",key:"15zrgr"}],["path",{d:"m14.5 4-5 16",key:"e7oirm"}]]),j={class:"registry-container"},L={class:"registry-header"},$={class:"stats-bar"},E={class:"stat-item"},F={class:"stat-item"},H={key:0,class:"loading-state"},Z={key:1,class:"error-state"},J={key:2,class:"registry-layout"},O={class:"registry-sidebar"},P=["onClick"],Y={class:"nav-icon"},G={class:"nav-info"},K={class:"nav-name"},Q={class:"nav-count"},U={key:0,class:"registry-main"},W={class:"tools-grid"},X={class:"tool-card-header"},ss={class:"tool-type-icon"},es={class:"tool-desc"},ts={class:"params-section"},as={class:"params-table"},ns={class:"code-text"},os={class:"type-text"},is={class:"status-cell"},ls={key:0,class:"required-badge"},ds={key:1,class:"optional-badge"},rs={class:"code-text dimmed"},cs={class:"technical-snippet"},us=b({__name:"Registry",setup(ps){const d=_([]),k=_(!0),m=_(null),u=_(null),f=async()=>{var c,a;try{const r=await R.get("/api/mcp/registry");d.value=r.data.services,d.value.length>0&&(u.value=d.value[0].id)}catch(r){m.value=((a=(c=r.response)==null?void 0:c.data)==null?void 0:a.detail)||r.message||"Erreur lors du chargement du registre"}finally{k.value=!1}};x(f);const C=()=>d.value.find(c=>c.id===u.value);return(c,a)=>{var r;return t(),n("div",j,[s("header",L,[a[0]||(a[0]=s("div",{class:"title-group"},[s("h1",null,"MCP Technical Registry"),s("p",null,"Vue consolidée des descripteurs techniques de tous les microservices intégrés.")],-1)),s("div",$,[s("div",E,[p(l(V),{size:"18"}),s("span",null,o(d.value.length)+" Services",1)]),s("div",F,[p(l(A),{size:"18"}),s("span",null,o(d.value.reduce((e,i)=>e+i.tools.length,0))+" Tools",1)])])]),k.value?(t(),n("div",H,[...a[1]||(a[1]=[s("div",{class:"spinner"},null,-1),q(" Chargement du registre technique... ",-1)])])):m.value?(t(),n("div",Z,[s("p",null,o(m.value),1),s("button",{onClick:f},"Réessayer")])):(t(),n("div",J,[s("aside",O,[(t(!0),n(y,null,g(d.value,e=>(t(),n("div",{key:e.id,class:z(["service-nav-item",{active:u.value===e.id}]),onClick:i=>u.value=e.id},[s("div",Y,[e.id==="users"?(t(),h(l(M),{key:0})):e.id==="items"?(t(),h(l(w),{key:1})):e.id==="drive"?(t(),h(l(D),{key:2})):(t(),h(l(S),{key:3}))]),s("div",G,[s("span",K,o(e.name),1),s("span",Q,o(e.tools.length)+" endpoints",1)]),p(l(B),{class:"nav-arrow",size:"16"})],10,P))),128))]),C()?(t(),n("main",U,[s("div",W,[(t(!0),n(y,null,g((r=C())==null?void 0:r.tools,e=>(t(),n("div",{key:e.name,class:"tool-card"},[s("div",X,[s("div",ss,[p(l(T),{size:"16"})]),s("h3",null,o(e.name),1)]),s("p",es,o(e.description),1),s("div",ts,[a[3]||(a[3]=s("div",{class:"params-header"},"Descripteur d'arguments :",-1)),s("div",as,[a[2]||(a[2]=s("div",{class:"param-row header"},[s("span",null,"Nom"),s("span",null,"Type"),s("span",null,"Requis"),s("span",null,"Défaut")],-1)),(t(!0),n(y,null,g(e.parameters,i=>(t(),n("div",{key:i.name,class:"param-row"},[s("span",ns,o(i.name),1),s("span",os,o(i.type),1),s("span",is,[i.required?(t(),n("span",ls,"Yes")):(t(),n("span",ds,"No"))]),s("span",rs,o(i.default||"-"),1)]))),128))])]),s("div",cs,[a[4]||(a[4]=s("div",{class:"snippet-header"},"JSON Spec",-1)),s("pre",null,[s("code",null,`{
  "method": "`+o(e.name)+`",
  "params": {
    `+o(e.parameters.map(i=>`"${i.name}": "${i.type}"`).join(`,
    `))+`
  }
}`,1)])])]))),128))])])):N("",!0)]))])}}}),ms=I(us,[["__scopeId","data-v-c7cb8eb2"]]);export{ms as default};
