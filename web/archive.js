import {$,h,finite} from './dom.js';
import {formatTime} from './player.js';
import {enhanceSelect,enhanceSearch} from './controls.js';

export const analysisLabels={queued:'В очереди',processing:'Проверяется',done:'Готово',failed:'Ошибка проверки',cancelled:'Отменено',interrupted:'Прервано',unknown:'Статус требует уточнения'};
export const reviewLabels={not_reviewed:'Не просмотрено',in_review:'Просматривается',reviewed:'Просмотрено'};
export function assetAvailable(run){
  if(run.asset?.available!==undefined)return !!run.asset.available;
  if(run.asset?.availability!==undefined)return run.asset.availability==='available';
  return !!run.video_available;
}

export class ArchiveView{
  constructor({request,onOpen,onReanalyze,onDelete,onAnalyze}){
    Object.assign(this,{request,onOpen,onReanalyze,onDelete,onAnalyze});this.offset=0;this.limit=3;this.total=0;this.revision=0;
    this.list=$('archive-list');this.error=$('archive-error');this.empty=$('archive-empty');this.search=$('archive-search');this.status=$('archive-filter');this.review=$('archive-review-filter');this.sort=$('archive-sort');
    this.status.replaceChildren(...Object.entries({all:'Все состояния',...analysisLabels}).map(([value,label])=>h('option',{value},label)));
    this.review.replaceChildren(...Object.entries({all:'Любой просмотр',...reviewLabels}).map(([value,label])=>h('option',{value},label)));
    this.sort.replaceChildren(h('option',{value:'desc'},'Сначала новые'),h('option',{value:'asc'},'Сначала старые'));
    enhanceSearch(this.search);this.filterControls=[this.status,this.review,this.sort].map(enhanceSelect);
    const reload=()=>{this.offset=0;this.load();};
    this.search.addEventListener('input',()=>{clearTimeout(this.searchTimer);this.searchTimer=setTimeout(reload,250);});
    for(const select of [this.status,this.review,this.sort])select.addEventListener('change',reload);
    $('archive-refresh-button').addEventListener('click',()=>this.load());
    $('archive-prev').addEventListener('click',()=>{this.offset=Math.max(0,this.offset-this.limit);this.load();});
    $('archive-next').addEventListener('click',()=>{if(this.offset+this.limit<this.total){this.offset+=this.limit;this.load();}});
    this.empty.replaceChildren(h('p',{},'Пока нет проверок'),h('button',{type:'button',class:'game-button',onclick:()=>onAnalyze()},'К анализу'));
  }
  async load(){
    const revision=++this.revision;this.error.hidden=true;$('archive-status').textContent='Загрузка истории…';
    const query=new URLSearchParams({search:this.search.value.trim(),sort:this.sort.value,limit:String(this.limit),offset:String(this.offset)});
    if(this.status.value!=='all')query.set('status',this.status.value);if(this.review.value!=='all')query.set('review_status',this.review.value);
    try{
      const response=await this.request(`/ui/v1/runs?${query}`);if(revision!==this.revision)return;
      this.total=finite(response.total);const runs=response.items||[];
      if(!runs.length&&this.offset>0){this.offset=Math.max(0,this.offset-this.limit);return this.load();}
      this.list.replaceChildren(...runs.map(run=>this.card(run)));this.empty.hidden=!!runs.length;
      if(!runs.length&&this.total===0&&(this.search.value||this.status.value!=='all'||this.review.value!=='all'))this.empty.firstElementChild.textContent='По этим условиям проверок нет';
      else this.empty.firstElementChild.textContent='Пока нет проверок';
      $('archive-status').textContent=`Проверок: ${this.total}`;
      $('archive-page').textContent=`${this.total?Math.floor(this.offset/this.limit)+1:1} / ${Math.max(1,Math.ceil(this.total/this.limit))}`;
      $('archive-prev').disabled=this.offset===0;$('archive-next').disabled=this.offset+this.limit>=this.total;
    }catch(error){if(revision!==this.revision)return;this.error.textContent=error.message;this.error.hidden=false;$('archive-status').textContent='История недоступна';}
  }
  refreshIfVisible(){if(!$('archive-scene').hidden){clearTimeout(this.refreshTimer);this.refreshTimer=setTimeout(()=>this.load(),250);}}
  card(run){
    const id=String(run.job_id||run.id),status=run.status||'unknown',created=new Date(run.created_at||run.created_at_utc||run.created_ts||'');
    const time=Number.isNaN(created.getTime())?'Дата неизвестна':created.toLocaleString('ru-RU');
    const count=status==='done'?`Эпизодов: ${finite(run.violation_count,run.result?.violations?.length||0)}`:'Количество эпизодов ещё не определено';
    const available=assetAvailable(run),card=h('article',{class:'archive-card','data-run-id':id});
    card.append(h('header',{class:'archive-card-head'},h('h3',{},run.filename||run.asset?.original_name||'Видео'),h('span',{class:`status-badge status-${status}`},analysisLabels[status]||analysisLabels.unknown)),
      h('p',{class:'archive-card-meta'},[time,run.duration_sec!=null?formatTime(finite(run.duration_sec)):null,count].filter(Boolean).join(' · ')),
      h('p',{},h('span',{class:'review-badge'},reviewLabels[run.review_status]||reviewLabels.not_reviewed),' · ',h('span',{class:'save-badge'},run.archive_status==='saved'?'Сохранено':run.archive_status==='partial'?'Сохранён только отчёт':run.archive_status==='save_failed'?'Ошибка сохранения':'Сохранение…')));
    if(!available)card.append(h('p',{class:'archive-warning'},'Видео недоступно. Сохранённый отчёт можно открыть.'));
    if(run.error)card.append(h('p',{class:'archive-warning'},run.error));
    const actions=h('div',{class:'archive-card-actions'},h('button',{type:'button',class:'game-button',onclick:()=>this.action(()=>this.onOpen(id))},'Открыть проверку'));
    if(available)actions.append(h('button',{type:'button',class:'game-button',onclick:()=>this.action(()=>this.onReanalyze(id))},'Проверить снова'));
    actions.append(h('button',{type:'button',class:'game-button',onclick:async()=>{
      if(!confirm(`Удалить проверку «${run.filename||id}»? Отчёт будет удалён. Копия видео удалится только если не используется другими проверками.`))return;
      await this.action(async()=>{await this.request(`/ui/v1/runs/${encodeURIComponent(id)}`,{method:'DELETE'});this.onDelete(id);await this.load();});
    }},'Удалить из истории'));
    card.append(actions);return card;
  }
  async action(callback){try{await callback();}catch(error){this.error.textContent=error.message;this.error.hidden=false;}}
}
