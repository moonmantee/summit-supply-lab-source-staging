<script setup>
const props=defineProps(['state','dirty']);const emit=defineEmits(['select','new','duplicate','save','discard','load']);
function select(event){emit('select',event.target.value,null);event.target.value=props.state.selectedId;}
function revision(event){emit('select',props.state.selectedId,Number(event.target.value));event.target.value=props.state.saved.revision;}
</script>
<template>
  <section class="box" aria-label="Schedule profile">
    <div class="ccdc-fields">
      <label class="field">Profile<div class="select is-fullwidth"><select aria-label="Profile" :value="state.selectedId" :disabled="state.busy||!state.connected" @change="select"><option value="" disabled>Unsaved new schedule</option><option v-for="profile in state.profiles" :value="profile.id" :key="profile.id">{{ profile.name }} ({{ profile.event_count }} events)</option></select></div></label>
      <label v-if="state.saved" class="field">Saved revision<div class="select"><select aria-label="Saved revision" :value="state.saved.revision" :disabled="state.busy" @change="revision"><option v-for="revision in state.saved.revisions" :value="revision" :key="revision">{{ revision }}</option></select></div></label>
      <p data-testid="saved-revision">{{ state.saved ? 'Saved revision '+state.saved.revision : 'Not saved' }}<span v-if="dirty" class="tag is-warning ml-2">Unsaved changes</span></p>
    </div>
    <div v-if="state.draft" class="ccdc-fields">
      <label class="field ccdc-grow">Profile name<input class="input" aria-label="Profile name" v-model="state.draft.name" maxlength="80" :disabled="state.busy"></label>
      <label class="field">Exercise duration<div class="select"><select aria-label="Exercise duration" v-model.number="state.draft.duration" :disabled="state.busy"><option v-for="duration in state.catalog.durations" :value="duration" :key="duration">{{ duration/3600 }} hours</option></select></div></label>
    </div>
    <div class="buttons">
      <button class="button" :disabled="state.busy" @click="$emit('new')">New</button><button class="button" :disabled="state.busy||!state.draft" @click="$emit('duplicate')">Duplicate profile</button>
      <button class="button is-primary" :disabled="state.busy||!state.connected||!dirty" @click="$emit('save')">Save revision</button><button class="button" :disabled="state.busy||!dirty" @click="$emit('discard')">Discard</button>
      <button class="button" :disabled="state.busy||!state.connected||dirty||!state.saved||['RUNNING','PAUSED'].includes(state.status?.exercise?.state)" @click="$emit('load')">Load</button>
    </div>
    <p class="help">Save creates a future revision. Load uses the saved revision and leaves the exercise disarmed. Stop before loading a different schedule.</p>
  </section>
</template>
