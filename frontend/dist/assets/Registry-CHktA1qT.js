import{c,d as x,o as b,b as a,e as s,f as p,u as l,t as o,h as q,F as m,m as y,g as w,r as _,l as t,p as I,j as h,_ as N}from"./index-8oU9MCma.js";import{D as R,C as z}from"./database-BygLZGcV.js";import{C as B}from"./chevron-right-Di4kYtgf.js";/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const M=c("ActivityIcon",[["path",{d:"M22 12h-4l-3 9L9 3l-3 9H2",key:"d5dnw9"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const S=c("BoxIcon",[["path",{d:"M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",key:"hh9hay"}],["path",{d:"m3.3 7 8.7 5 8.7-5",key:"g66t2b"}],["path",{d:"M12 22V12",key:"d0xqtd"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const T=c("CloudIcon",[["path",{d:"M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z",key:"p7xjir"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const V=c("Code2Icon",[["path",{d:"m18 16 4-4-4-4",key:"1inbqp"}],["path",{d:"m6 8-4 4 4 4",key:"15zrgr"}],["path",{d:"m14.5 4-5 16",key:"e7oirm"}]]);/**
 * @license lucide-vue-next v0.300.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const D=c("TerminalIcon",[["polyline",{points:"4 17 10 11 4 5",key:"akl6gq"}],["line",{x1:"12",x2:"20",y1:"19",y2:"19",key:"q2wloq"}]]),j={class:"registry-container"},A={class:"registry-header"},E={class:"stats-bar"},L={class:"stat-item"},$={class:"stat-item"},F={key:0,class:"loading-state"},H={key:1,class:"error-state"},Z={key:2,class:"registry-layout"},J={class:"registry-sidebar"},O=["onClick"],P={class:"nav-icon"},Y={class:"nav-info"},G={class:"nav-name"},K={class:"nav-count"},Q={key:0,class:"registry-main"},U={class:"tools-grid"},W={class:"tool-card-header"},X={class:"tool-type-icon"},ss={class:"tool-desc"},es={class:"params-section"},ts={class:"params-table"},as={class:"code-text"},ns={class:"type-text"},os={class:"status-cell"},is={key:0,class:"required-badge"},ls={key:1,class:"optional-badge"},rs={class:"code-text dimmed"},ds={class:"technical-snippet"},cs=x({__name:"Registry",setup(us){const r=_([]),g=_(!0),v=_(null),u=_(null),k=async()=>{try{const d=await fetch("/api/mcp/registry");if(!d.ok)throw new Error("Erreur lors du chargement du registre");const n=await d.json();r.value=n.services,r.value.length>0&&(u.value=r.value[0].id)}catch(d){v.value=d.message}finally{g.value=!1}};b(k);const f=()=>r.value.find(d=>d.id===u.value);return(d,n)=>{var C;return t(),a("div",j,[s("header",A,[n[0]||(n[0]=s("div",{class:"title-group"},[s("h1",null,"MCP Technical Registry"),s("p",null,"Vue consolidée des descripteurs techniques de tous les microservices intégrés.")],-1)),s("div",E,[s("div",L,[p(l(M),{size:"18"}),s("span",null,o(r.value.length)+" Services",1)]),s("div",$,[p(l(V),{size:"18"}),s("span",null,o(r.value.reduce((e,i)=>e+i.tools.length,0))+" Tools",1)])])]),g.value?(t(),a("div",F,[...n[1]||(n[1]=[s("div",{class:"spinner"},null,-1),q(" Chargement du registre technique... ",-1)])])):v.value?(t(),a("div",H,[s("p",null,o(v.value),1),s("button",{onClick:k},"Réessayer")])):(t(),a("div",Z,[s("aside",J,[(t(!0),a(m,null,y(r.value,e=>(t(),a("div",{key:e.id,class:I(["service-nav-item",{active:u.value===e.id}]),onClick:i=>u.value=e.id},[s("div",P,[e.id==="users"?(t(),h(l(R),{key:0})):e.id==="items"?(t(),h(l(S),{key:1})):e.id==="drive"?(t(),h(l(T),{key:2})):(t(),h(l(z),{key:3}))]),s("div",Y,[s("span",G,o(e.name),1),s("span",K,o(e.tools.length)+" endpoints",1)]),p(l(B),{class:"nav-arrow",size:"16"})],10,O))),128))]),f()?(t(),a("main",Q,[s("div",U,[(t(!0),a(m,null,y((C=f())==null?void 0:C.tools,e=>(t(),a("div",{key:e.name,class:"tool-card"},[s("div",W,[s("div",X,[p(l(D),{size:"16"})]),s("h3",null,o(e.name),1)]),s("p",ss,o(e.description),1),s("div",es,[n[3]||(n[3]=s("div",{class:"params-header"},"Descripteur d'arguments :",-1)),s("div",ts,[n[2]||(n[2]=s("div",{class:"param-row header"},[s("span",null,"Nom"),s("span",null,"Type"),s("span",null,"Requis"),s("span",null,"Défaut")],-1)),(t(!0),a(m,null,y(e.parameters,i=>(t(),a("div",{key:i.name,class:"param-row"},[s("span",as,o(i.name),1),s("span",ns,o(i.type),1),s("span",os,[i.required?(t(),a("span",is,"Yes")):(t(),a("span",ls,"No"))]),s("span",rs,o(i.default||"-"),1)]))),128))])]),s("div",ds,[n[4]||(n[4]=s("div",{class:"snippet-header"},"JSON Spec",-1)),s("pre",null,[s("code",null,`{
  "method": "`+o(e.name)+`",
  "params": {
    `+o(e.parameters.map(i=>`"${i.name}": "${i.type}"`).join(`,
    `))+`
  }
}`,1)])])]))),128))])])):w("",!0)]))])}}}),vs=N(cs,[["__scopeId","data-v-ed9eb686"]]);export{vs as default};
