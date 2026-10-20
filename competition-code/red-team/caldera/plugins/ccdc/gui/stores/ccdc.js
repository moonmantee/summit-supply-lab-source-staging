import { reactive, computed } from 'vue';
const clone = value => JSON.parse(JSON.stringify(value));
export const eventId = () => 'event-' + crypto.randomUUID().replaceAll('-', '');
export function formatTime(seconds = 0) {
  seconds = Math.floor(seconds);
  return [Math.floor(seconds/3600),Math.floor(seconds/60)%60,seconds%60].map(n=>String(n).padStart(2,'0')).join(':');
}
export function parseTime(value) {
  if(!/^\d{2}:\d{2}:\d{2}$/.test(value))throw Error('Use HH:MM:SS');
  const [h,m,s]=value.split(':').map(Number);
  if(m>59||s>59)throw Error('Minutes and seconds must be below 60');
  return h*3600+m*60+s;
}
export async function requestApi(path, method='GET', body=null) {
  const response=await fetch('/plugin/ccdc/api/'+path,{method,credentials:'same-origin',cache:'no-store',
    headers:body?{'Content-Type':'application/json','X-CCDC-Request':'1'}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(8000)});
  let result;
  try{result=await response.json();}catch{throw Error(response.status===401?'Sign in to CALDERA again':'Controller request rejected');}
  if(!response.ok||!result.ok){const error=Error(result.error?.message||'Controller request rejected');error.rows=result.error?.rows||[];error.code=result.error?.code;throw error;}
  return result.data;
}
export function createCcdcStore(api=requestApi) {
  const state=reactive({status:null,catalog:{capabilities:[],durations:[10800,12600,14400]},profiles:[],selectedId:'',saved:null,draft:null,connected:false,initialized:false,busy:false,error:'',rows:[],pending:null});
  const dirty=computed(()=>!!state.draft&&(!state.saved||JSON.stringify(state.draft)!==JSON.stringify(state.saved.document)));
  let selectionVersion=0;
  async function refresh(){
    if(!state.initialized)return bootstrap();
    try{state.status=await api('status');state.connected=true;}catch{state.connected=false;}
  }
  async function profiles(){state.profiles=(await api('profiles')).profiles;}
  async function selectProfile(id,revision=null){
    if(state.busy)return;
    if(dirty.value&&!window.confirm('Discard unsaved schedule changes?'))return;
    const version=++selectionVersion,before=JSON.stringify(state.draft);state.busy=true;
    try{const saved=await api('profiles/'+encodeURIComponent(id)+(revision===null?'':'?revision='+revision));
      if(version!==selectionVersion||JSON.stringify(state.draft)!==before){state.error='Schedule changed while selecting a profile; your edits were kept';return;}
      state.selectedId=id;state.saved=saved;state.draft=clone(saved.document);state.rows=[];state.error='';}
    catch(error){state.error=error.message;}
    finally{if(version===selectionVersion)state.busy=false;}
  }
  async function bootstrap(){
    try{const result=await api('bootstrap');state.status=result;state.catalog=result.catalog;state.profiles=result.profiles;state.connected=true;state.initialized=true;state.error='';
      const id=result.snapshot?.profile_id||result.profiles.find(p=>p.id==='first3h-all')?.id||result.profiles[0]?.id;
      if(id)await selectProfile(id);
    }catch(error){state.connected=false;state.error=error.message;}
  }
  function newProfile(){if(state.busy||dirty.value&&!window.confirm('Discard unsaved schedule changes?'))return;state.selectedId='';state.saved=null;state.draft={name:'New schedule',duration:10800,events:[]};state.error='';state.rows=[];}
  function duplicateProfile(){if(state.busy||!state.draft)return;const draft=clone(state.draft);draft.name=(draft.name+' copy').slice(0,80);state.selectedId='';state.saved=null;state.draft=draft;state.error='';state.rows=[];}
  function discardDraft(){if(state.busy)return;if(state.saved)state.draft=clone(state.saved.document);else state.draft={name:'New schedule',duration:10800,events:[]};state.error='';state.rows=[];}
  async function mutation(path,method,args){
    const identity=JSON.stringify({path,method,args});
    if(!state.pending||state.pending.identity!==identity)state.pending={identity,body:{args,expected_exercise_id:state.status?.exercise?.id||null,expected_lifecycle_revision:state.status?.lifecycle_revision,idempotency_key:crypto.randomUUID().replaceAll('-','')}};
    const data=await api(path,method,state.pending.body);state.pending=null;return data;
  }
  async function perform(fn){if(state.busy||!state.connected)return;state.busy=true;state.error='';state.rows=[];
    try{await fn();await profiles();await refresh();}catch(error){state.error=error.message;state.rows=error.rows||[];if(error.code==='conflict')state.pending=null;await refresh();}finally{state.busy=false;}}
  async function saveDraft(){return perform(async()=>{
    const args={document:clone(state.draft)};if(state.saved)args.expected_profile_revision=state.saved.head_revision;
    const saved=await mutation(state.saved?'profiles/'+encodeURIComponent(state.selectedId):'profiles',state.saved?'PUT':'POST',args);
    state.saved=saved;state.selectedId=saved.id;state.draft=clone(saved.document);
  });}
  async function loadSelected(){return perform(async()=>{
    if(dirty.value||!state.saved)throw Error('Save or discard changes before loading');
    await mutation('exercise/load','POST',{profile_id:state.selectedId,revision:state.saved.revision});
  });}
  async function control(action){return perform(()=>mutation('exercise/'+action,'POST',{}));}
  return {state,dirty,bootstrap,refresh,selectProfile,newProfile,duplicateProfile,saveDraft,discardDraft,loadSelected,control};
}
