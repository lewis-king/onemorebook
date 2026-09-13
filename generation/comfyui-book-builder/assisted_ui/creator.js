'use strict';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api='/book-builder/creator/api';
const sid=location.pathname.split('/')[3]||null;
let state=null,viewStage=null,choice=null,busy=false,renderKey='',lastCurrent=null,offline=false;
function notice(message){$('notice').textContent=message;$('notice').hidden=!message;}
async function request(path,body){const response=await fetch(path,{cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json','X-Book-Creator':'1'},body:JSON.stringify(body)}:{})});const result=await response.json();if(!response.ok)throw Error(result.error||`Request failed (${response.status})`);return result;}
function currentView(){return state.stages.find(s=>s.id===viewStage)||state.stages.find(s=>s.id===state.current_stage);}
function candidate(){const stage=currentView();return stage.candidates.find(c=>c.id===choice)||stage.candidates.find(c=>c.id===stage.selected)||stage.candidates.at(-1);}
function modelLabel(info){return info.method==='human_text_revision'?'Your revised draft':info.model||'Saved draft';}
function modelDetails(info){return [modelLabel(info),info.method?.replaceAll('_',' '),info.steps?`${info.steps} steps · guidance ${info.guidance} · ${info.sampler}`:'',info.seed?`Seed ${info.seed}`:''].filter(Boolean).join(' · ');}
function runningJob(){return currentView().id===state.current_stage&&['queued','generating','ready'].includes(state.status)?state.job:null;}
function renderReferences(id,refs){
  const html=(refs||[]).map((r,i)=>{
    const url=r.url||'/book-builder/books/'+encodeURIComponent(state.id)+'/'+r.path.split('/').map(encodeURIComponent).join('/');
    return `<a class="reference" href="${esc(url)}" target="_blank" rel="noopener"><img src="${esc(url)}" alt="${esc(r.label)}">Image ${i+1} · ${esc(r.label)}</a>`;
  }).join('');
  if($(id).innerHTML!==html)$(id).innerHTML=html;
}
function promptView(){
  const stage=currentView(),c=candidate(),isCurrent=stage.id===state.current_stage;
  if(isCurrent&&['queued','generating','exporting','ready'].includes(state.status)&&state.job){
    return {text:state.job.generation?.prompt||'',help:state.job.generation?.prompt
      ?`Being used for attempt ${state.job.attempt}${state.job.generation.method==='image_edit'?' · image edit':''}.`
      :'Preparing the prompt. It will appear here when ready.'};
  }
  if(isCurrent&&stage.status!=='approved'&&stage.kind==='scene'&&stage.prompt_base){
    return {text:stage.prompt_base.prompt,help:'Regenerate uses this prompt. Add feedback to revise it. Edit this image uses your feedback to change the selected image.'};
  }
  return {text:c?.metadata.prompt||'',help:c?`Used for attempt ${c.attempt}.`:'The prompt will appear here when ready.'};
}
function renderPrompt(){
  const stage=currentView(),c=candidate(),view=promptView(),job=runningJob();
  const custom=$('prompt-override').value.trim();
  $('prompt-details').hidden=!view.text&&!c&&!state.job;
  $('prompt-text').textContent=custom||view.text;
  $('prompt-text').hidden=!(custom||view.text)||Boolean(custom&&$('override-details').open);
  $('prompt-help').textContent=custom?'Your edited prompt will be used as written for the next attempt.':view.help;
  $('attempt-details').hidden=!c;
  $('attempt-details-label').textContent=`Attempt ${c?.attempt??''} details · ${job?'previously saved model & references':'model & reference images'}`;
  // Active inputs arrive after prompt preparation, independently of the saved preview.
  // Never borrow a previous candidate's images while these inputs are still unknown.
  $('generation-context').hidden=!job;
  $('generation-label').textContent=job?.generation?`Attempt ${job.attempt} · references being used now`:'The model and reference images will appear when this attempt is prepared.';
  $('generation-model').textContent=job?.generation?modelDetails(job.generation):'';
  renderReferences('generation-references',job?.generation?.reference_images);
  // Keep historical provenance behind an explicit disclosure, never relabel it as the next prompt.
  $('attempt-prompt').hidden=!c?.metadata.prompt||c.metadata.prompt===view.text&&!custom;
  $('override-details').hidden=['story','plan'].includes(stage.kind)||stage.status==='approved'||stage.id!==state.current_stage;
  const editable=stage.id===state.current_stage&&['awaiting_review','error','ready'].includes(state.status)&&!busy;
  $('prompt-override').disabled=!editable;$('use-prompt').disabled=!editable||!view.text;
}
function renderStoryGuide(guide){
  if(!guide)return '';
  const choices=[guide.flavour,guide.read_aloud].filter(Boolean).map(esc).join(' · ');
  const pages=guide.page_count??guide.pages?.length;
  return `<p class="helper">${pages?esc(pages)+' pages · ':''}${esc(guide.words)} words · Ages ${esc(guide.age_range)}${choices?'<br>'+choices:''}</p><details><summary>A few things to listen for</summary><ul class="review-questions">${guide.questions.map(q=>`<li>${esc(q)}</li>`).join('')}</ul><p class="helper small">These are prompts for your review, not an automated score.</p></details>`;
}
function renderContent(stage,c){
  if(!c)return '<div class="placeholder"><div><h2>Your next chapter starts here.</h2><p>The next candidate will appear here as soon as it is saved.</p></div></div>';
  if(!['story','plan'].includes(stage.kind)){
    if(stage.source_photo_url){
      return '<div class="moment-compare"><figure><img src="'+esc(stage.source_photo_url)+'" alt="The original photograph"><figcaption>The photograph</figcaption></figure>'
        +'<figure><a href="'+esc(c.url)+'" target="_blank" rel="noopener" aria-label="Open full-size storybook illustration"><img class="art" src="'+esc(c.url)+'" alt="Storybook illustration — attempt '+c.attempt+'"></a><figcaption>'+(stage.kind==='moment'?'Storybook restyle':'Storybook page')+' · attempt '+c.attempt+'</figcaption></figure></div>';
    }
    return `<a href="${esc(c.url)}" target="_blank" rel="noopener" aria-label="Open full-size image"><img class="art" src="${esc(c.url)}" alt="${esc(stage.title)} — attempt ${c.attempt}"></a>`;
  }
  const value=c.metadata.content;
  if(c.metadata.validation_error)return '<div class="text-preview"><h2>This draft needs a correction</h2><div class="error">'+esc(c.metadata.validation_error)+'</div><p>You can regenerate with feedback or edit the JSON below. It must satisfy the story contract before approval.</p><pre>'+esc(JSON.stringify(value,null,2))+'</pre></div>';
  if(!value)return '<div class="text-preview">Open the saved candidate to read this draft.</div>';
  if(stage.kind==='story')return '<div class="text-preview"><h2>'+esc(value.story.metadata.title)+'</h2><div class="brief">'+esc(value.story.metadata.bookSummary)+'</div>'+value.story.pages.map(p=>`<h3>PAGE ${p.pageNumber}</h3><p>${esc(p.text)}</p><details><summary>Illustration brief</summary><div class="brief">${esc(p.imagePrompt)}</div></details>`).join('')+'<h3>CANONICAL CHARACTERS</h3>'+value.production.characters.map(c=>`<div class="character-note"><strong>${esc(c.name)}</strong><div>${esc(c.appearance)}</div><small>${esc(c.height_cm||'Height not specified')} cm</small></div>`).join('')+'</div>';
  return '<div class="text-preview"><h2>Our visual plan</h2><div class="brief">'+esc(value.continuity_notes)+'</div><h3>REUSABLE REFERENCES</h3>'+value.assets.map(a=>`<div class="character-note"><strong>${esc(a.name)}</strong> · ${esc(a.kind.replaceAll('_',' '))}<div>${esc(a.appearance)}</div>${a.kind==='prop_state'?`<small>Built from: ${esc(a.source_assets.join(', '))} · Used on pages: ${esc(a.visible_pages.join(', '))}</small>`:''}</div>`).join('')+value.scenes.map(s=>`<h3>${s.page?'PAGE '+s.page:'COVER'}</h3><p>${esc(s.moment)}</p><div class="brief">Cast: ${esc(s.character_refs.join(', ')||'None')}<br>Objects & places: ${esc(s.asset_refs.join(', ')||'None')}</div>`).join('')+'</div>';
}
function render(){
  if(!state)return;
  if(state.creator_url&&location.pathname!==state.creator_url)history.replaceState(null,'',state.creator_url+location.search+location.hash);
  $('home').hidden=true;$('studio').hidden=false;
  if(lastCurrent!==state.current_stage){viewStage=state.current_stage;choice=null;renderKey='';lastCurrent=state.current_stage;}
  const stage=currentView(),c=candidate(),isCurrent=stage.id===state.current_stage;
  $('book-title').textContent=state.title||'Your new book';
  const approved=state.stages.filter(s=>s.status==='approved').length;
  $('overall').textContent=`${approved} of ${state.stages.length} steps approved · Saved locally`;
  $('stages').innerHTML=state.stages.map(s=>`<button class="stage-nav ${s.id===stage.id?'viewing':''} ${s.id===state.current_stage?'active':''}" data-stage="${esc(s.id)}" ${s.status==='pending'&&s.id!==state.current_stage?'disabled':''}><span class="mark">${s.status==='approved'?'✓':s.id===state.current_stage?'◉':'○'}</span>${esc(s.title)}</button>`).join('');
  $('stage-title').textContent=stage.title;$('kind').textContent=stage.kind==='scene'?'MAKE THE STORY VISIBLE':stage.kind==='story'?'BEGIN WITH A STORY':stage.kind==='plan'?'PLAN THE WORLD':stage.kind==='moment'?'YOUR MOMENTS, STORYBOOK STYLE':'BUILD YOUR REFERENCE LIBRARY';
  $('status').textContent=stage.status==='approved'?'Approved':state.status==='complete'?'Book complete':isCurrent?state.status.replaceAll('_',' '):stage.status.replaceAll('_',' ');
  const working=isCurrent&&['queued','generating','exporting','ready'].includes(state.status);
  const job=runningJob();
  $('candidate-caption').hidden=!c||!job||c.attempt===job.attempt;
  $('candidate-caption').textContent=c&&job?`Showing saved attempt ${c.attempt}. Attempt ${job.attempt} is ${job.generation?'generating':'being prepared'}; its result will appear when ready.`:'';
  $('work-status').hidden=!working;
  const styleTakes=stage.kind==='style'&&state.job?stage.candidates.filter(c=>(c.metadata.style_inspiration||'')===(state.config?.art_inspiration||'')).length:0;
  $('work-label').textContent=state.status==='exporting'?'Saving your finished book…':state.job?.stage_id==='style.png'?`Flux2 Turbo 8 is creating style option ${styleTakes+1} of 4…`:state.job?.generation?'Flux2 Turbo 8 is creating your candidate…':['story','plan'].includes(stage.kind)?'Gemma 4 is preparing your draft…':'Preparing this image…';
  $('work-detail').textContent=state.job?.prompt_id?`ComfyUI job ${state.job.prompt_id.slice(0,8)} · Attempt ${state.job.attempt}. You can leave this page; progress is saved.`:'This step will pause for your review when it is ready.';
  if(working&&state.job?.created_at){const elapsed=Math.max(0,Math.floor((Date.now()-Date.parse(state.job.created_at))/1000));$('work-detail').textContent+=` ${Math.floor(elapsed/60)}m ${elapsed%60}s elapsed.`;}
  $('stage-error').hidden=!isCurrent||!state.error;$('stage-error').textContent=state.error||'';
  const key=stage.id+':'+(c?.id||'none')+':'+(c?.sha256||'')+':'+(c?.metadata.validation_error||'');
  if(key!==renderKey){
    renderKey=key;$('candidate-view').innerHTML=renderContent(stage,c);
    $('feedback').value='';$('prompt-override').value='';
    $('attempt-details').open=false;$('override-details').open=false;
    $('style-inspiration').value=state.config?.art_inspiration||'';
    $('draft-json').value=c?.metadata.content?JSON.stringify(c.metadata.content,null,2):'';
    const info=c?.metadata||{};$('exact-prompt').textContent=info.prompt||'No model prompt: this candidate was edited directly.';
    $('story-guide').hidden=stage.kind!=='story'||!info.story_guide;
    $('story-guide').innerHTML=stage.kind==='story'?renderStoryGuide(info.story_guide):'';
    $('review-hint').textContent=stage.kind==='story'?'Try a few pages aloud. Look for a story your child can follow, join in with and want to hear again. You decide when it is ready.':stage.kind==='plan'?'Check each scene against the page text, including the joke or feeling and what must stay consistent.':stage.kind==='moment'?'Check that the day is still recognisable — the people, the moment, the feeling — now drawn in the book\'s art style.':stage.kind==='style'?'Four takes on the book\'s art style arrive one by one. Compare them all, then approve the one you want — every later step follows it.':stage.kind==='scene'&&stage.source_photo_url?'This page recreates a real photograph. Check the people, poses and key details against the original — the storybook scene should stay true to the day.':'Check the action, characters and recurring details. Your decision controls what happens next.';
    $('feedback').placeholder=stage.kind==='story'?'What would make this more engaging? Point to a page, an awkward line or a choice that does not make sense.':stage.kind==='plan'?'Which moment should we show? Mention any recurring object, action or visual joke that needs attention.':'What should change? For example: keep the heron on the left; remove the extra heron on the right.';
    $('model-info').textContent=modelDetails(info);
    renderReferences('references',info.reference_images);
    $('candidate-file').href=c?.url||'#';
  }
  renderPrompt();
  $('regenerate').textContent='Regenerate';
  $('feedback').placeholder=stage.kind==='scene'&&stage.prompt_base?'Optional: describe a change to the prompt. Leave empty to try it again.':$('feedback').placeholder;
  const original=state.page_revision?.stage_id===stage.id?state.page_revision.original.selected:null;
  $('attempts').innerHTML=stage.candidates.map(a=>`<button class="attempt ${a.id===c?.id?'selected':''}" data-attempt="${esc(a.id)}">${['story','plan'].includes(stage.kind)?'<span class="text-thumb">Aa</span>':`<img src="${esc(a.url)}" alt="Attempt ${a.attempt}" loading="lazy">`}Attempt ${a.attempt}${a.id===original?' · Original':stage.status==='approved'&&a.id===stage.selected?' ✓':''}</button>`).join('');
  $('page-copy').innerHTML=stage.text?'<p class="eyebrow">ON THIS PAGE</p><p>'+esc(stage.text)+'</p>':'';
  const locked=stage.status==='approved';$('locked').hidden=!locked&&isCurrent;$('decision-content').hidden=locked||!isCurrent;
  $('style-inspiration-block').hidden=$('decision-content').hidden||stage.kind!=='style';
  $('locked').querySelector('h2').textContent=c?.id===stage.selected?'Approved and saved.':'Earlier attempt';
  $('locked').querySelector('p').textContent=c?.id===stage.selected?(stage.kind==='scene'?'This is the approved image. You can revise it and approve a replacement.':'This is the approved version. You can revise it any time; steps that use it will be regenerated with the replacement.'):'This attempt was kept for comparison. The candidate marked ✓ is the approved version.';
  if(!locked&&!isCurrent){
    $('locked').querySelector('h2').textContent='Saved for later.';
    $('locked').querySelector('p').textContent='Finish the step you are working on, or keep its original, to continue here.';
  }
  const revisable=['scene','style','character','character_state','moment','prop','prop_state','location'].includes(stage.kind);
  $('reopen-page').hidden=!state.can_revise_pages||!locked||!revisable;
  $('reopen-page').textContent=stage.kind==='scene'?(stage.id==='cover.png'?'Revise this cover':'Revise this page'):'Revise this reference';
  $('reopen-page').disabled=busy||Boolean(state.page_revision)||!['awaiting_review','error','ready','complete'].includes(state.status);
  $('reopen-help').hidden=$('reopen-page').hidden||($('reopen-page').disabled?false:stage.kind==='scene');
  $('reopen-help').textContent=state.page_revision?'Finish the step you are revising, or keep its original, before reopening another.':stage.kind!=='scene'?'Revise with feedback as usual. Approving the replacement marks every approved step that uses this reference — portraits, pages — for regeneration with the new version.':'Wait for the current generation to finish, then reopen this page.';
  const canDecide=isCurrent&&['awaiting_review','error','ready'].includes(state.status)&&!busy;
  $('approve').disabled=!canDecide||!c;$('regenerate').disabled=!canDecide;
  $('approve').textContent=original?'Approve replacement & return →':'Approve & continue →';
  $('keep-original').hidden=!original||!isCurrent;$('keep-original').disabled=!canDecide;
  $('edit-image').hidden=['story','plan'].includes(stage.kind);$('edit-image').disabled=!canDecide||!c;
  $('save-draft').disabled=!canDecide||!c;
  $('json-editor').hidden=!['story','plan'].includes(stage.kind);
  $('resume').hidden=!isCurrent||!['error','queued','generating','exporting'].includes(state.status);
  $('resume').disabled=busy;
  $('finished-link').hidden=!state.book_url;$('finished-link').href=state.book_url||'#';
  const publication=state.publication||{};
  const published=publication.status==='complete'&&publication.url;
  $('publish-book').hidden=state.status!=='complete'||Boolean(published);
  $('publish-book').disabled=busy;
  $('publish-book').textContent=publication.status==='publishing'?'Publishing to library…':publication.status==='error'?'Retry publish to library ↗':'Publish to library ↗';
  $('published-link').hidden=!published;$('published-link').href=publication.url||'#';
  $('publish-status').hidden=!publication.status||publication.status==='complete';
  $('publish-status').textContent=publication.status==='publishing'?'Uploading the approved export to Supabase. You can leave this page open; the upload is resumable.':publication.error||'';
}
async function act(action){
  if(busy)return;
  const c=candidate();let content;
  if(action==='save_draft'){try{content=JSON.parse($('draft-json').value)}catch{notice('The draft must be valid JSON. Check the edited text.');return;}}
  if(action==='edit'&&!$('feedback').value.trim()&&!$('prompt-override').value.trim()){notice('Describe the change you want in the feedback box.');$('feedback').focus();return;}
  busy=true;render();notice('');
  try{state=await request(api+'/'+sid,{action,revision:state.revision,stage_id:currentView().id,candidate_id:c?.id,feedback:$('feedback').value,prompt_override:$('prompt-override').value,content,...(currentView().kind==='style'?{art_inspiration:$('style-inspiration').value.trim()}:{})});choice=null;renderKey='';}
  catch(error){notice(error.message);try{state=await request(api+'/'+sid)}catch{}}
  finally{busy=false;render();}
}
$('approve').onclick=()=>act('approve');$('regenerate').onclick=()=>act('regenerate');$('edit-image').onclick=()=>act('edit');$('save-draft').onclick=()=>act('save_draft');$('resume').onclick=()=>act('resume');
$('reopen-page').onclick=()=>act('reopen');$('keep-original').onclick=()=>act('keep_original');
$('publish-book').onclick=()=>act('publish');
$('use-prompt').onclick=()=>{$('prompt-override').value=promptView().text;renderPrompt();$('prompt-override').focus();};
$('prompt-override').oninput=()=>renderPrompt();
$('override-details').ontoggle=()=>{if(state)renderPrompt();};
$('return-current').onclick=()=>{viewStage=state.current_stage;choice=null;renderKey='';render();};
$('stages').onclick=e=>{const b=e.target.closest('[data-stage]');if(b&&!b.disabled){viewStage=b.dataset.stage;choice=null;renderKey='';render();}};
$('attempts').onclick=e=>{const b=e.target.closest('[data-attempt]');if(b){choice=b.dataset.attempt;renderKey='';render();}};
const MAX_PHOTOS=14;
let dragRow=null;
function momentRows(){return [...document.querySelectorAll('.photo-row')];}
function updateOrder(){momentRows().forEach((row,i)=>{row.querySelector('.photo-order').textContent=i+1;
  const [up,down]=row.querySelectorAll('.photo-move');up.disabled=i===0;down.disabled=i===momentRows().length-1;});
  const note=$('photo-count-note');const count=momentRows().length;
  note.hidden=!count;note.textContent=count?`${count} photograph${count===1?'':'s'} → ${count} page${count===1?'':'s'}, in this order. The story follows the day, one page per photograph.`:'';
}
function refreshPhotoAdd(){const rows=momentRows();$('add-photo').disabled=rows.length>=MAX_PHOTOS;
  $('add-photo').textContent=rows.length?'Add more photographs':'Add photographs';updateOrder();}
function photoRow(file){
  const row=document.createElement('div');row.className='photo-row';
  row.innerHTML='<span class="photo-grip" draggable="true" title="Drag to reorder">⠿</span><span class="photo-order" aria-hidden="true"></span><div class="photo-picker"><img class="photo-thumb" alt="Photograph preview" hidden><button type="button" class="photo-zoom" hidden>View larger</button></div>'
    +'<input type="text" class="photo-caption" maxlength="500" placeholder="Caption — who or what is in this photo? For example: Esme blowing out the candles on the tractor cake.">'
    +'<div class="photo-row-actions"><button type="button" class="photo-move text-button">Move up</button><button type="button" class="photo-move text-button">Move down</button><button type="button" class="photo-remove text-button">Remove</button></div>';
  const thumb=row.querySelector('.photo-thumb'),zoom=row.querySelector('.photo-zoom');
  const setFile=chosen=>{if(row._photo)URL.revokeObjectURL(row._photo.url);
    const url=URL.createObjectURL(chosen);row._photo={file:chosen,url};
    thumb.src=url;thumb.hidden=false;zoom.hidden=false;};
  if(file)setFile(file);
  const open=()=>{if(row._photo)openLightbox(row._photo.url);};
  thumb.onclick=open;zoom.onclick=open;
  const [up,down]=row.querySelectorAll('.photo-move');
  up.onclick=()=>{const previous=row.previousElementSibling;if(previous){row.parentNode.insertBefore(row,previous);refreshPhotoAdd();}};
  down.onclick=()=>{const next=row.nextElementSibling;if(next){row.parentNode.insertBefore(next,row);refreshPhotoAdd();}};
  row.querySelector('.photo-remove').onclick=()=>{if(row._photo)URL.revokeObjectURL(row._photo.url);row.remove();refreshPhotoAdd();};
  const grip=row.querySelector('.photo-grip');
  grip.ondragstart=event=>{dragRow=row;event.dataTransfer.effectAllowed='move';event.dataTransfer.setData('text/plain','');row.classList.add('dragging');};
  grip.ondragend=()=>{dragRow=null;row.classList.remove('dragging');
    momentRows().forEach(r=>r.classList.remove('drop-above','drop-below'));};
  row.ondragover=event=>{if(!dragRow||dragRow===row)return;event.preventDefault();event.dataTransfer.dropEffect='move';
    const rect=row.getBoundingClientRect();const above=event.clientY-rect.top<rect.height/2;
    row.classList.toggle('drop-above',above);row.classList.toggle('drop-below',!above);};
  row.ondragleave=()=>row.classList.remove('drop-above','drop-below');
  row.ondrop=event=>{if(!dragRow)return;event.preventDefault();
    const rect=row.getBoundingClientRect();const above=event.clientY-rect.top<rect.height/2;
    row.parentNode.insertBefore(dragRow,above?row:row.nextSibling);
    row.classList.remove('drop-above','drop-below');refreshPhotoAdd();};
  return row;
}
const lightbox=document.createElement('div');lightbox.className='photo-lightbox';lightbox.hidden=true;
lightbox.innerHTML='<img alt="Photograph, enlarged"><button type="button" class="photo-lightbox-close" aria-label="Close enlarged view">✕</button>';
document.body.appendChild(lightbox);
function openLightbox(url){lightbox.querySelector('img').src=url;lightbox.hidden=false;document.body.classList.add('photo-lightbox-open');}
function closeLightbox(){lightbox.hidden=true;lightbox.querySelector('img').src='';document.body.classList.remove('photo-lightbox-open');}
lightbox.onclick=event=>{if(event.target===lightbox||event.target.closest('.photo-lightbox-close'))closeLightbox();};
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!lightbox.hidden)closeLightbox();});
async function uploadPhoto(file){
  const body=new FormData();body.append('file',file);
  const response=await fetch('/book-builder/creator/upload',{method:'POST',headers:{'X-Book-Creator':'1'},body});
  const result=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(result.error||`Upload failed (${response.status})`);
  return result.upload_id;
}
function selectedMode(){return document.querySelector('input[name="mode"]:checked')?.value||'scratch';}
document.querySelectorAll('input[name="mode"]').forEach(radio=>radio.onchange=()=>{
  const moment=selectedMode()==='moment';
  $('moment-fields').hidden=!moment;$('idea-fields').hidden=moment;notice('');});
const photoPicker=$('photo-picker');
$('add-photo').onclick=()=>{if(momentRows().length<MAX_PHOTOS)photoPicker.click();};
photoPicker.onchange=()=>{
  for(const file of photoPicker.files){
    if(momentRows().length>=MAX_PHOTOS){notice(`Up to ${MAX_PHOTOS} photographs.`);break;}
    $('photo-rows').appendChild(photoRow(file));}
  photoPicker.value='';refreshPhotoAdd();};
$('new-book').onsubmit=async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;notice('');
  try{
    let data;
    if(selectedMode()==='moment'){
      const description=$('moment-description').value.trim();
      if(!description){notice('Tell us about the day this book should remember.');$('moment-description').focus();b.disabled=false;return;}
      const rows=momentRows();
      if(!rows.length){notice('Add at least one photograph.');b.disabled=false;return;}
      const photos=[];
      for(const [index,row] of rows.entries()){
        const photo=row._photo;
        const caption=row.querySelector('.photo-caption').value.trim();
        if(!photo||!photo.file){notice(`Choose photograph ${index+1}.`);b.disabled=false;return;}
        if(!caption){notice(`Give photograph ${index+1} a short caption.`);row.querySelector('.photo-caption').focus();b.disabled=false;return;}
        b.textContent=`Uploading photograph ${index+1} of ${rows.length}…`;
        photos.push({upload_id:await uploadPhoto(photo.file),caption});
      }
      data={mode:'moment',story_idea:'',moment:{description,photos},art_inspiration:$('moment-art-inspiration').value.trim()};
    }else{
      data=Object.fromEntries(new FormData(e.target));data.mode='scratch';
    }
    b.textContent='Starting your book…';
    const result=await request(api,data);location.href='/book-builder/create/'+result.id;
  }catch(error){notice(error.message);b.disabled=false;b.textContent='Generate →';}};
async function poll(){if(busy)return;try{state=await request(api+'/'+sid);if(offline){notice('');offline=false;}render();}catch(error){offline=true;notice('Cannot reach the book creator. Your saved work stays on disk. Reconnect to ComfyUI to continue.');}}
async function init(){if(sid){await poll();setInterval(poll,3000);}else{$('home').hidden=false;try{const sessions=await request(api);$('sessions').innerHTML=sessions.length?sessions.map(s=>`<a class="session" href="${esc(s.creator_url||'/book-builder/create/'+s.id)}"><strong>${esc(s.title||'Untitled book')}</strong><span>${esc(s.status.replaceAll('_',' '))} · ${esc(new Date(s.updated_at).toLocaleString())}</span></a>`).join(''):'<p class="helper">Your books will appear here.</p>';}catch(error){notice(error.message);}}}
init();
