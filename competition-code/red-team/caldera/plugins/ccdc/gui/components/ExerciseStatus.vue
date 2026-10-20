<script setup>
import {formatTime} from '../stores/ccdc';
defineProps(['status','connected','busy']);defineEmits(['control','refresh']);
</script>
<template>
  <section class="box" aria-label="Exercise controls">
    <div class="ccdc-status">
      <div><p class="heading">Exercise state</p><strong data-testid="exercise-state">{{ status?.exercise?.state || 'Unavailable' }}</strong><p class="ccdc-clock">{{ formatTime(status?.exercise?.elapsed) }}</p></div>
      <div><p class="heading">Loaded schedule</p><p data-testid="loaded-revision">{{ status?.snapshot?.document?.name || 'No loaded schedule' }}<template v-if="status?.snapshot?.revision"> · revision {{ status.snapshot.revision }}</template></p><p>{{ status?.snapshot?.document?.events?.length || 0 }} events</p></div>
      <div><p class="heading">Scoring</p><p>{{ status?.scoring?.id ? 'Event '+status.scoring.id : 'Unavailable' }} · {{ status?.scoring?.state || 'Unknown' }}</p><p>{{ status?.scoring?.fresh ? 'Fresh' : 'Stale or unavailable' }}<template v-if="status?.scoring?.age != null"> · {{ status.scoring.age.toFixed(1) }}s</template></p></div>
    </div>
    <p v-if="!connected" class="notification is-warning" role="status">Controller unavailable — displayed state is stale</p>
    <div class="buttons mt-4">
      <button class="button is-primary" :disabled="!connected||busy||status?.exercise?.state!=='DISARMED'||!status?.snapshot?.document?.events?.length||!status?.scoring?.fresh||status?.scoring?.state!=='RUNNING'||status?.scoring?.id!==status?.exercise?.scoring_event_id" @click="$emit('control','start')">Start</button>
      <button class="button" :disabled="!connected||busy||status?.exercise?.state!=='RUNNING'" @click="$emit('control','pause')">Pause</button>
      <button class="button is-primary" :disabled="!connected||busy||status?.exercise?.state!=='PAUSED'||!status?.scoring?.fresh||status?.scoring?.state!=='RUNNING'||status?.scoring?.id!==status?.exercise?.scoring_event_id" @click="$emit('control','resume')">Resume</button>
      <button class="button is-danger is-outlined" :disabled="!connected||busy||!['DISARMED','RUNNING','PAUSED'].includes(status?.exercise?.state)" @click="$emit('control','stop')">Stop</button>
      <button class="button is-text" :disabled="busy" @click="$emit('refresh')">Refresh status</button>
    </div>
    <p class="help">Pause freezes exercise time. Stop revokes future actions. Accepted business faults require contestant repair.</p>
  </section>
</template>
