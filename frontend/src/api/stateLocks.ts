import { apiClient } from './config'

export interface StateLockEntryDTO {
  key: string
  label: string
  value: unknown
  source: string
  kind: string
  status: 'normal' | 'violated' | 'manually_modified'
  metadata: Record<string, unknown>
}

export interface StateLockGroupDTO {
  entries: StateLockEntryDTO[]
}

export interface StateLockSnapshotDTO {
  state_lock_id: string
  chapter_id: string
  version: number
  plan_version: number
  source: string
  change_reason: string
  changed_fields: string[]
  inference_notes: string[]
  critical_change: Record<string, unknown>
  time_lock: StateLockGroupDTO
  location_lock: StateLockGroupDTO
  character_lock: StateLockGroupDTO
  item_lock: StateLockGroupDTO
  numeric_lock: StateLockGroupDTO
  event_lock: StateLockGroupDTO
  ending_lock: StateLockGroupDTO
}

export interface UpdateStateLocksRequest {
  change_reason: string
  time_lock: StateLockGroupDTO
  location_lock: StateLockGroupDTO
  character_lock: StateLockGroupDTO
  item_lock: StateLockGroupDTO
  numeric_lock: StateLockGroupDTO
  event_lock: StateLockGroupDTO
  ending_lock: StateLockGroupDTO
}

export const stateLocksApi = {
  generateStateLocks: (chapterId: string, planVersion?: number) =>
    apiClient.post<StateLockSnapshotDTO>(`/chapters/${chapterId}/state-locks`, planVersion ? { plan_version: planVersion } : {}) as Promise<StateLockSnapshotDTO>,

  getCurrentStateLocks: (chapterId: string) =>
    apiClient.get<StateLockSnapshotDTO>(`/chapters/${chapterId}/state-locks/current`) as Promise<StateLockSnapshotDTO>,

  updateStateLocks: (stateLockId: string, data: UpdateStateLocksRequest) =>
    apiClient.patch<StateLockSnapshotDTO>(`/state-locks/${stateLockId}`, data) as Promise<StateLockSnapshotDTO>,
}
