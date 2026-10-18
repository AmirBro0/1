export const $=id=>document.getElementById(id);
export function h(tag,attrs={},...children){
  const node=document.createElement(tag);
  for(const [key,value]of Object.entries(attrs||{})){
    if(value===undefined||value===null||value===false)continue;
    if(key==='class')node.className=value;
    else if(key==='text')node.textContent=value;
    else if(key.startsWith('on')&&typeof value==='function')node.addEventListener(key.slice(2),value);
    else node.setAttribute(key,value===true?'':String(value));
  }
  for(const child of children.flat(Infinity))if(child!==null&&child!==undefined&&child!==false)node.append(child.nodeType?child:document.createTextNode(String(child)));
  return node;
}
export function imageSrc(value){return typeof value==='string'&&value?value.startsWith('data:image/')?value:`data:image/jpeg;base64,${value}`:'';}
export function externalLink(url,label,attrs={}){
  const link=h('a',attrs,label);
  try{const parsed=new URL(url);if(['https:','http:'].includes(parsed.protocol)){link.href=parsed.href;link.target='_blank';link.rel='noopener noreferrer';}}catch{/* Untrusted model links stay plain text. */}
  return link;
}
export async function copyText(value,button){
  const original=button.textContent;
  try{
    if(navigator.clipboard?.writeText)await navigator.clipboard.writeText(value);
    else{const input=h('textarea',{'aria-label':'Полный текст для копирования'});input.value=value;document.body.append(input);input.select();const copied=document.execCommand('copy');input.remove();if(!copied)throw new Error('Clipboard unavailable');}
    button.textContent='Скопировано';
  }catch{button.textContent='Копирование недоступно';}
  setTimeout(()=>{button.textContent=original;},1800);
}
export const finite=(value,fallback=0)=>Number.isFinite(Number(value))?Number(value):fallback;
export const terminal=status=>['done','failed','cancelled','completed'].includes(status);
