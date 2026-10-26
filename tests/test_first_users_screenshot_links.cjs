const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
// Substitute DOM effects; execute the actual app report renderer. No browser or network.
function render(result,key){
 const roots=new Map();
 class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.textContent='';this.classList={toggle(){}};}
  append(...xs){this.children.push(...xs);}
  replaceChildren(...xs){this.children=[...xs];}
 }
 const document={querySelector(s){if(!roots.has(s))roots.set(s,new Element('root'));return roots.get(s);},querySelectorAll(){return[];},createElement(tag){return new Element(tag);}};
 const context=vm.createContext({document,fetch:()=>new Promise(()=>{}),URLSearchParams,location:{search:''}});
 vm.runInContext(fs.readFileSync(process.env.FIRST_USERS_SCRIPT||path.join(__dirname,'../workspace/first-users.js'),'utf8'),context);
 context.result=result;context.key=key;vm.runInContext('showReport(result,key)',context);
 return roots.get('#screens');
}
test('each screenshot gets its own full-size original link, including capability reports',()=>{
 for(const key of ['local-report-id','capability-token']){
  const screens=[{image:'step 01.png',label:'Start'},{image:'step-02.png',label:'Guide'}];
  const root=render({screens,checks:[]},key);assert.equal(root.children.length,2);
  root.children.forEach((figure,i)=>{
   const img=figure.children.find(e=>e.tagName==='img');const link=figure.children.find(e=>e.tagName==='a');
   assert.equal(img.src,`/screen/${key}/${encodeURIComponent(screens[i].image)}`);
   assert.equal(link.href,img.src);assert.equal(link.target,'_blank');assert.equal(link.rel,'noopener noreferrer');
   assert.equal(link.textContent,'Open full-size screenshot (new tab)');
  });
 }
});
test('untrusted screenshot labels remain text and cannot supply a link target',()=>{
 const label='<a href="https://outside.invalid">elsewhere</a>';
 const root=render({screens:[{image:'../x?y#z.png',label}],checks:[]},'cap');
 const [img,caption,link]=root.children[0].children;
 assert.equal(img.alt,label);assert.equal(caption.textContent,label);
 assert.equal(link.href,'/screen/cap/..%2Fx%3Fy%23z.png');assert.equal(caption.children.length,0);
 assert.equal(render({screens:[],checks:[]},'cap').children.length,0);
});
