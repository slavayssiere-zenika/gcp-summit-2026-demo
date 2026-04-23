<script setup lang="ts">
import { HardDriveUpload } from 'lucide-vue-next'
import PageHeader from '../components/ui/PageHeader.vue'
import CVReanalysisPanel from '../components/CVReanalysisPanel.vue'
import DriveAdminPanel from '../components/DriveAdminPanel.vue'
import CVImportMonitor from '../components/CVImportMonitor.vue'
</script>

<template>
  <div class="admin-wrapper fade-in">

    <PageHeader
      title="Supervision Ingestion & Réanalyse"
      subtitle="Gérez les sources Drive, le pipeline IA et forcez la réanalyse de profils ciblés."
      :icon="HardDriveUpload"
      :breadcrumb="[{ label: 'Administration' }]"
    />

    <CVReanalysisPanel />
    <CVImportMonitor />
    <DriveAdminPanel />

  </div>
</template>

<style scoped>
.admin-wrapper {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
}
.fade-in { animation: fadeIn 0.35s ease forwards; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

@media (max-width: 768px) {
  .admin-wrapper { padding: 1rem; gap: 1.25rem; }
}
</style>
