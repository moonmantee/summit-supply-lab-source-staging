<script setup>
import {computed,ref} from 'vue';import {formatTime} from '../stores/ccdc';
const props=defineProps(['events','status','rows','busy','loadedMatches']);defineEmits(['add','edit','duplicate','delete']);
const guest=ref(''),action=ref('');
const guests=computed(()=>[...new Set(props.events.map(e=>e.guest))].sort());const actions=computed(()=>[...new Set(props.events.map(e=>e.action))].sort());
const filtered=computed(()=>props.events.filter(e=>(!guest.value||e.guest===guest.value)&&(!action.value||e.action===action.value)).toSorted((a,b)=>a.at-b.at||a.id.localeCompare(b.id)));
function outcome(event){if(!props.loadedMatches)return 'Future revision';const found=props.status?.outcomes?.find(e=>e.event===event.id);if(found)return found.outcome;return props.status?.exercise?.elapsed>=event.at+event.window?'Window elapsed; no confirmed dispatch':'Pending';}
function invalid(event){return props.rows?.some(row=>row.id===event.id);}
</script>
<template>
  <section class="box" aria-label="Schedule events">
    <div class="ccdc-fields"><h2 class="title is-5 ccdc-grow">Schedule · {{ events.length }} events</h2><button class="button is-primary" :disabled="busy||events.length>=256" @click="$emit('add')">Add event</button></div>
    <div class="ccdc-fields"><label>Filter guest<div class="select"><select aria-label="Filter guest" v-model="guest"><option value="">All guests</option><option v-for="value in guests" :key="value">{{ value }}</option></select></div></label><label>Filter action<div class="select"><select aria-label="Filter action" v-model="action"><option value="">All actions</option><option v-for="value in actions" :key="value">{{ value }}</option></select></div></label><span>{{ filtered.length }} shown</span></div>
    <div class="table-container"><table class="table is-fullwidth is-hoverable"><thead><tr><th>Time</th><th>Guest</th><th>Action / target</th><th>Outcome</th><th>Event controls</th></tr></thead><tbody><tr v-for="event in filtered" :key="event.id" :class="{'has-background-danger-dark':invalid(event)}"><td class="ccdc-clock">{{ formatTime(event.at) }}</td><td>{{ event.guest }}</td><td>{{ event.action.replaceAll('_',' ') }}<small class="ccdc-muted">{{ event.target }} · {{ event.id }}</small></td><td>{{ outcome(event) }}</td><td><div class="buttons are-small"><button class="button" :disabled="busy" @click="$emit('edit',event)">Edit event</button><button class="button" :disabled="busy||events.length>=256" @click="$emit('duplicate',event)">Duplicate event</button><button class="button" :disabled="busy" @click="$emit('delete',event)">Delete event</button></div></td></tr></tbody></table></div>
    <p v-if="!events.length">Add an event to build a schedule. Empty schedules can be loaded for cleanup but cannot start.</p>
  </section>
</template>
