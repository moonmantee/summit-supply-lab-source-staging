<script setup>
import {ref,onMounted,onBeforeUnmount,computed,getCurrentInstance} from 'vue';
import {createCcdcStore,eventId} from '../stores/ccdc';
import ExerciseStatus from '../components/ExerciseStatus.vue';import ProfileEditor from '../components/ProfileEditor.vue';import ScheduleTable from '../components/ScheduleTable.vue';import EventForm from '../components/EventForm.vue';import GuestReadiness from '../components/GuestReadiness.vue';
const store=createCcdcStore(),{state,dirty}=store;const form=ref(false),editing=ref(null);let timer,refreshing=false,removeGuard;
const router=getCurrentInstance().appContext.config.globalProperties.$router;
if(router)removeGuard=router.beforeEach((to,from)=>to.path===from.path||!dirty.value||window.confirm('Discard unsaved schedule changes?'));
const loadedMatches=computed(()=>!dirty.value&&state.saved&&state.selectedId===state.status?.snapshot?.profile_id&&state.saved.revision===state.status?.snapshot?.revision);
function edit(event=null){editing.value=event;form.value=true;}
function apply(event){const index=state.draft.events.findIndex(e=>e.id===event.id);if(index<0)state.draft.events.push(event);else state.draft.events[index]=event;form.value=false;}
function duplicate(event){state.draft.events.push({...event,id:eventId()});}
function remove(event){state.draft.events=state.draft.events.filter(e=>e.id!==event.id);}
function leave(event){if(dirty.value){event.preventDefault();event.returnValue='';}}
onMounted(async()=>{await store.bootstrap();window.addEventListener('beforeunload',leave);timer=setInterval(async()=>{if(refreshing||state.busy)return;refreshing=true;try{await store.refresh();}finally{refreshing=false;}},2000);});
onBeforeUnmount(()=>{clearInterval(timer);removeGuard?.();window.removeEventListener('beforeunload',leave);});
</script>
<template><section class="ccdc"><div class="ccdc-page-heading"><div><h1 class="title is-3">CCDC Exercise</h1><p class="subtitle is-6">Schedule and control the competition from one place.</p></div><span class="tag">Fixed lab actions</span></div>
  <ExerciseStatus :status="state.status" :connected="state.connected" :busy="state.busy" @control="store.control" @refresh="store.refresh"/>
  <div v-if="state.error" class="notification is-danger" role="alert"><p>{{ state.error }}</p><ul v-if="state.rows.length"><li v-for="(row,index) in state.rows" :key="index">{{ row.id||'Row '+(row.index+1) }}: {{ row.message }}</li></ul></div>
  <ProfileEditor :state="state" :dirty="dirty" @select="store.selectProfile" @new="store.newProfile" @duplicate="store.duplicateProfile" @save="store.saveDraft" @discard="store.discardDraft" @load="store.loadSelected"/>
  <ScheduleTable v-if="state.draft" :events="state.draft.events" :status="state.status" :rows="state.rows" :busy="state.busy" :loaded-matches="loadedMatches" @add="edit()" @edit="edit" @duplicate="duplicate" @delete="remove"/>
  <GuestReadiness :guests="state.status?.guests||[]"/>
  <EventForm v-if="form" :event="editing" :catalog="state.catalog" @apply="apply" @cancel="form=false"/>
</section></template>
<style>
.ccdc{padding:24px;max-width:1700px;margin:auto}.ccdc-page-heading,.ccdc-fields,.ccdc-status{display:flex;gap:24px;align-items:center;flex-wrap:wrap;margin-bottom:20px}.ccdc-page-heading{justify-content:space-between}.ccdc-status>div{flex:1;min-width:200px}.ccdc-status strong{font-size:1.2rem}.ccdc-clock{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace}.ccdc-grow{flex:1;min-width:220px}.ccdc .field{margin-bottom:12px}.ccdc .ccdc-muted{display:block;opacity:.7;font-size:.75rem;overflow-wrap:anywhere}.ccdc table td{vertical-align:middle}.ccdc .table-container{max-height:650px;overflow:auto}.ccdc thead{position:sticky;top:0;background:#252525;z-index:1}.ccdc .buttons{flex-wrap:wrap}.ccdc-readiness{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px}.ccdc .modal-card{max-width:94vw}.ccdc details summary{cursor:pointer}.ccdc .heading{margin-bottom:8px}.ccdc .help{font-size:.85rem;line-height:1.5}.ccdc select{max-width:100%}@media(max-width:800px){.ccdc{padding:12px}.ccdc-fields{gap:12px}.ccdc table{min-width:850px}.ccdc-status{gap:16px}.ccdc .button{min-height:36px}}
</style>
