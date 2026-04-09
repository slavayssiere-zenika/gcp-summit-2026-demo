import{c as h,d as b,o as x,b as a,e as s,f as u,u as l,t as o,h as w,F as m,m as y,g as q,r as p,l as t,p as N,j as _,C as R,_ as z}from"./index-Cygip0XA.js";import{D as B,C as I}from"./database-Cz2cPp0Q.js";import{T as M}from"./terminal-D7kmbo2G.js";/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=h("ActivityIcon",[["path",{d:"M22 12h-4l-3 9L9 3l-3 9H2",key:"d5dnw9"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=h("BoxIcon",[["path",{d:"M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",key:"hh9hay"}],["path",{d:"m3.3 7 8.7 5 8.7-5",key:"g66t2b"}],["path",{d:"M12 22V12",key:"d0xqtd"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=h("CloudIcon",[["path",{d:"M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z",key:"p7xjir"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=h("Code2Icon",[["path",{d:"m18 16 4-4-4-4",key:"1inbqp"}],["path",{d:"m6 8-4 4 4 4",key:"15zrgr"}],["path",{d:"m14.5 4-5 16",key:"e7oirm"}]]),j={class:"registry-container"},A={class:"registry-header"},E={class:"stats-bar"},L={class:"stat-item"},$={class:"stat-item"},F={key:0,class:"loading-state"},H={key:1,class:"error-state"},Z={key:2,class:"registry-layout"},J={class:"registry-sidebar"},O=["onClick"],P={class:"nav-icon"},Y={class:"nav-info"},G={class:"nav-name"},K={class:"nav-count"},Q={key:0,class:"registry-main"},U={class:"tools-grid"},W={class:"tool-card-header"},X={class:"tool-type-icon"},ss={class:"tool-desc"},es={class:"params-section"},ts={class:"params-table"},as={class:"code-text"},ns={class:"type-text"},os={class:"status-cell"},is={key:0,class:"required-badge"},ls={key:1,class:"optional-badge"},ds={class:"code-text dimmed"},rs={class:"technical-snippet"},cs=b({__name:"Registry",setup(us){const d=p([]),g=p(!0),v=p(null),c=p(null),k=async()=>{try{const r=await fetch("/api/mcp/registry");if(!r.ok)throw new Error("Erreur lors du chargement du registre");const n=await r.json();d.value=n.services,d.value.length>0&&(c.value=d.value[0].id)}catch(r){v.value=r.message}finally{g.value=!1}};x(k);const f=()=>d.value.find(r=>r.id===c.value);return(r,n)=>{var C;return t(),a("div",j,[s("header",A,[n[0]||(n[0]=s("div",{class:"title-group"},[s("h1",null,"MCP Technical Registry"),s("p",null,"Vue consolidée des descripteurs techniques de tous les microservices intégrés.")],-1)),s("div",E,[s("div",L,[u(l(S),{size:"18"}),s("span",null,o(d.value.length)+" Services",1)]),s("div",$,[u(l(D),{size:"18"}),s("span",null,o(d.value.reduce((e,i)=>e+i.tools.length,0))+" Tools",1)])])]),g.value?(t(),a("div",F,[...n[1]||(n[1]=[s("div",{class:"spinner"},null,-1),w(" Chargement du registre technique... ",-1)])])):v.value?(t(),a("div",H,[s("p",null,o(v.value),1),s("button",{onClick:k},"Réessayer")])):(t(),a("div",Z,[s("aside",J,[(t(!0),a(m,null,y(d.value,e=>(t(),a("div",{key:e.id,class:N(["service-nav-item",{active:c.value===e.id}]),onClick:i=>c.value=e.id},[s("div",P,[e.id==="users"?(t(),_(l(B),{key:0})):e.id==="items"?(t(),_(l(T),{key:1})):e.id==="drive"?(t(),_(l(V),{key:2})):(t(),_(l(I),{key:3}))]),s("div",Y,[s("span",G,o(e.name),1),s("span",K,o(e.tools.length)+" endpoints",1)]),u(l(R),{class:"nav-arrow",size:"16"})],10,O))),128))]),f()?(t(),a("main",Q,[s("div",U,[(t(!0),a(m,null,y((C=f())==null?void 0:C.tools,e=>(t(),a("div",{key:e.name,class:"tool-card"},[s("div",W,[s("div",X,[u(l(M),{size:"16"})]),s("h3",null,o(e.name),1)]),s("p",ss,o(e.description),1),s("div",es,[n[3]||(n[3]=s("div",{class:"params-header"},"Descripteur d'arguments :",-1)),s("div",ts,[n[2]||(n[2]=s("div",{class:"param-row header"},[s("span",null,"Nom"),s("span",null,"Type"),s("span",null,"Requis"),s("span",null,"Défaut")],-1)),(t(!0),a(m,null,y(e.parameters,i=>(t(),a("div",{key:i.name,class:"param-row"},[s("span",as,o(i.name),1),s("span",ns,o(i.type),1),s("span",os,[i.required?(t(),a("span",is,"Yes")):(t(),a("span",ls,"No"))]),s("span",ds,o(i.default||"-"),1)]))),128))])]),s("div",rs,[n[4]||(n[4]=s("div",{class:"snippet-header"},"JSON Spec",-1)),s("pre",null,[s("code",null,`{
  "method": "`+o(e.name)+`",
  "params": {
    `+o(e.parameters.map(i=>`"${i.name}": "${i.type}"`).join(`,
    `))+`
  }
}`,1)])])]))),128))])])):q("",!0)]))])}}}),vs=z(cs,[["__scopeId","data-v-ed9eb686"]]);export{vs as default};
