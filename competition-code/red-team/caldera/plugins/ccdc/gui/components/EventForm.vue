<script setup>
import {computed,reactive,ref,watch} from 'vue';import {eventId,formatTime,parseTime} from '../stores/ccdc';
const props=defineProps(['event','catalog']);const emit=defineEmits(['apply','cancel']);const error=ref('');
const first=props.catalog.capabilities[0]||{};
const draft=reactive(props.event?JSON.parse(JSON.stringify(props.event)):{id:eventId(),guest:first.guest||'',action:first.action||'notice',target:first.target||'desktop',at:0,window:15});const time=ref(formatTime(draft.at));
const guests=computed(()=>[...new Set(props.catalog.capabilities.map(c=>c.guest))]);
const actions=computed(()=>[...new Set(props.catalog.capabilities.filter(c=>c.guest===draft.guest).map(c=>c.action))]);
const targets=computed(()=>[...new Set(props.catalog.capabilities.filter(c=>c.guest===draft.guest&&c.action===draft.action).map(c=>c.target))]);
watch(()=>draft.guest,()=>{if(!actions.value.includes(draft.action))draft.action=actions.value[0]||'';if(!targets.value.includes(draft.target))draft.target=targets.value[0]||'';});
watch(()=>draft.action,()=>{if(!targets.value.includes(draft.target))draft.target=targets.value[0]||'';if(draft.action==='notice')delete draft.duration;else draft.duration??=180;});
function apply(){try{const event={...draft,at:parseTime(time.value)};if(!targets.value.includes(event.target))throw Error('Select an accepted target');if(event.action!=='notice')event.duration=Number(event.duration||180);else delete event.duration;emit('apply',event);}catch(e){error.value=e.message;}}
</script>
<template>
  <div class="modal is-active"><div class="modal-background" @click="$emit('cancel')"></div><section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="event-title"><header class="modal-card-head"><h2 class="modal-card-title" id="event-title">{{ event?'Edit event':'Add event' }}</h2><button class="delete" aria-label="Close event editor" @click="$emit('cancel')"></button></header><form @submit.prevent="apply"><div class="modal-card-body">
    <p v-if="error" class="notification is-danger" role="alert">{{ error }}</p>
    <label class="field is-block">Relative time<input class="input" aria-label="Relative time" v-model="time" placeholder="HH:MM:SS" required pattern="[0-9]{2}:[0-9]{2}:[0-9]{2}"></label>
    <label class="field is-block">Guest<div class="select is-fullwidth"><select aria-label="Guest" v-model="draft.guest"><option v-for="guest in guests" :key="guest">{{ guest }}</option></select></div></label>
    <label class="field is-block">Action<div class="select is-fullwidth"><select aria-label="Action" v-model="draft.action"><option v-for="action in actions" :key="action" :value="action">{{ action.replaceAll('_',' ') }}</option></select></div></label>
    <label class="field is-block">Target<div class="select is-fullwidth"><select aria-label="Target" v-model="draft.target"><option v-for="target in targets" :key="target">{{ target }}</option></select></div></label>
    <details class="mt-4"><summary>Advanced timing</summary><label class="field is-block">Acceptance window (seconds)<input class="input" aria-label="Acceptance window" type="number" v-model.number="draft.window" min="1" max="15" required></label><label v-if="draft.action!=='notice'" class="field is-block">Reservation (seconds)<input class="input" aria-label="Reservation" type="number" v-model.number="draft.duration" min="15" max="180" required></label><p class="help">Reservation bounds dispatch overlap. It does not restore a business service; contestants must repair accepted faults.</p></details>
  </div><footer class="modal-card-foot"><button class="button is-primary" type="submit">Apply event</button><button class="button" type="button" @click="$emit('cancel')">Cancel</button></footer></form></section></div>
</template>
