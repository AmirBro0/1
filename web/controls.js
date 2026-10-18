import {h} from './dom.js';

let controlId=0;
let openDropdown=null;

// The hidden select remains the source of truth for filters and API requests.
// The visible control never opens an operating system menu.
export function enhanceSelect(select){
  const parent=select.parentElement,label=parent.firstChild?.textContent?.trim()||select.getAttribute('aria-label')||'Выбор';
  const field=h('div',{class:'control-field'}),labelId=`control-label-${++controlId}`,listId=`control-list-${controlId}`;
  field.append(h('span',{class:'control-label',id:labelId},label));parent.replaceWith(field);field.append(select);select.hidden=true;select.tabIndex=-1;select.setAttribute('aria-hidden','true');
  const value=h('span',{class:'choice-value',id:`control-value-${controlId}`}),button=h('button',{type:'button',class:'choice-trigger','aria-haspopup':'listbox','aria-expanded':'false','aria-labelledby':`${labelId} ${value.id}`,'aria-controls':listId},value,h('span',{class:'choice-chevron','aria-hidden':'true'},'⌄'));
  const list=h('div',{id:listId,class:'choice-menu',role:'listbox',tabindex:-1,'aria-labelledby':labelId,hidden:true});
  field.append(button);document.body.append(list);
  let active=0,typed='',typeTimer;
  const options=()=>[...select.options].filter(option=>!option.disabled);
  const rows=()=>[...list.children];
  const sync=()=>{value.textContent=select.selectedOptions[0]?.textContent||'Выбрать';button.disabled=select.disabled;for(const row of rows())row.setAttribute('aria-selected',String(row.dataset.value===select.value));};
  const position=()=>{
    if(list.hidden)return;
    const rect=button.getBoundingClientRect();if(!button.getClientRects().length){close();return;}
    const width=Math.min(Math.max(rect.width,220),innerWidth-24),below=innerHeight-rect.bottom-10,above=rect.top-10;
    list.style.width=`${width}px`;list.style.left=`${Math.max(12,Math.min(rect.left,innerWidth-width-12))}px`;
    list.style.maxHeight=`${Math.max(80,Math.min(300,Math.max(below,above)-8))}px`;
    const height=list.getBoundingClientRect().height;
    list.style.top=`${below>=height||below>=above?Math.min(rect.bottom+6,innerHeight-height-8):Math.max(8,rect.top-height-6)}px`;
  };
  const focusOption=index=>{const items=rows();if(!items.length)return;active=(index+items.length)%items.length;for(const [i,row]of items.entries())row.classList.toggle('is-focused',i===active);list.setAttribute('aria-activedescendant',items[active].id);items[active].scrollIntoView({block:'nearest'});};
  const close=(restore=false)=>{list.hidden=true;button.setAttribute('aria-expanded','false');if(openDropdown===api)openDropdown=null;if(restore)button.focus();};
  const choose=index=>{const option=options()[index];if(!option)return;select.value=option.value;sync();close(true);select.dispatchEvent(new Event('change',{bubbles:true}));};
  const open=(direction=0)=>{
    openDropdown?.close();openDropdown=api;
    list.replaceChildren(...options().map((option,index)=>h('div',{id:`${listId}-${index}`,class:'choice-option',role:'option','data-value':option.value,'aria-selected':String(option.value===select.value),onpointerdown:event=>event.preventDefault(),onclick:()=>choose(index),onpointermove:()=>focusOption(index)},h('span',{},option.textContent),h('span',{class:'choice-check','aria-hidden':'true'},'✓'))));
    list.hidden=false;button.setAttribute('aria-expanded','true');position();list.focus({preventScroll:true});
    const selected=options().findIndex(option=>option.value===select.value);focusOption(direction<0?rows().length-1:Math.max(0,selected));
  };
  const api={close,open,sync,button,list};
  button.addEventListener('click',()=>list.hidden?open():close());
  button.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close(true);}else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();open(event.key==='ArrowUp'||event.key==='End'?-1:0);}});
  list.addEventListener('keydown',event=>{
    if(event.key==='Escape'){event.preventDefault();close(true);}
    else if(event.key==='Tab'){event.preventDefault();close(true);if(event.shiftKey){const focusable=[...document.querySelectorAll('button,input,a[href],[tabindex="0"]')].filter(node=>node.getClientRects().length&&!node.disabled);focusable[Math.max(0,focusable.indexOf(button)-1)]?.focus();}else{const focusable=[...document.querySelectorAll('button,input,a[href],[tabindex="0"]')].filter(node=>node.getClientRects().length&&!node.disabled);focusable[focusable.indexOf(button)+1]?.focus();}}
    else if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();focusOption(event.key==='Home'?0:event.key==='End'?rows().length-1:active+(event.key==='ArrowDown'?1:-1));}
    else if(['Enter',' '].includes(event.key)){event.preventDefault();choose(active);}
    else if(event.key.length===1&&!event.ctrlKey&&!event.metaKey){clearTimeout(typeTimer);typed+=event.key.toLocaleLowerCase('ru');typeTimer=setTimeout(()=>{typed='';},700);const index=options().findIndex(option=>option.textContent.toLocaleLowerCase('ru').startsWith(typed));if(index>=0)focusOption(index);}
  });
  select.addEventListener('change',sync);document.addEventListener('pointerdown',event=>{if(!field.contains(event.target)&&!list.contains(event.target))close();});
  document.addEventListener('focusin',event=>{if(!field.contains(event.target)&&!list.contains(event.target))close();});
  window.addEventListener('resize',position);window.addEventListener('scroll',position,true);window.addEventListener('hashchange',()=>close());sync();return api;
}

export function enhanceSearch(input){
  const parent=input.parentElement,label=parent.firstChild?.textContent?.trim()||'Поиск';
  const field=h('div',{class:'control-field archive-search-field'}),caption=h('label',{class:'control-label',for:input.id},label);
  const clear=h('button',{type:'button',class:'search-clear','aria-label':'Очистить поиск',hidden:!input.value},'×'),box=h('div',{class:'archive-search-box'},h('span',{class:'search-glyph','aria-hidden':'true'}),input,clear);
  parent.replaceWith(field);field.append(caption,box);input.setAttribute('aria-label','Поиск по названию видео');input.placeholder='Найти видео…';
  input.addEventListener('input',()=>{clear.hidden=!input.value;});clear.addEventListener('click',()=>{input.value='';clear.hidden=true;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();});
}

export function segmentedReview(onChange){
  const choices=[['not_reviewed','Не просмотрено'],['in_review','Смотрю'],['reviewed','Просмотрено']],buttons=[];
  let value='not_reviewed';const group=h('div',{class:'review-segments',role:'radiogroup','aria-label':'Просмотр человеком'});
  const sync=()=>{for(const [index,button]of buttons.entries()){const selected=choices[index][0]===value;button.setAttribute('aria-checked',String(selected));button.tabIndex=selected?0:-1;}};
  const choose=index=>{value=choices[index][0];sync();buttons[index].focus();onChange(value);};
  for(const [index,[key,label]]of choices.entries()){
    const button=h('button',{type:'button',class:'review-segment',role:'radio','data-value':key,'aria-checked':String(index===0),tabindex:index===0?0:-1,onclick:()=>choose(index)},h('span',{class:'review-segment-dot','aria-hidden':'true'}),label);
    button.addEventListener('keydown',event=>{if(['ArrowRight','ArrowDown','ArrowLeft','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();choose(event.key==='Home'?0:event.key==='End'?choices.length-1:(index+(['ArrowRight','ArrowDown'].includes(event.key)?1:choices.length-1))%choices.length);}});buttons.push(button);group.append(button);
  }
  return {element:group,get value(){return value;},set value(next){value=choices.some(([key])=>key===next)?next:'not_reviewed';sync();}};
}
