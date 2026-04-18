import { apiClient } from './config'

export interface FusionSuspenseBudget {
  primary: number
  secondary: number
}

export interface CreateFusionJobRequest {
  plan_version: number
  state_lock_version: number
  beat_ids: string[]
  target_words: number
  suspense_budget: FusionSuspenseBudget
}

export interface FusionDraftDTO {
  fusion_id: string
  chapter_id: string
  plan_version: number
  state_lock_version: number
  status: string
  text: string
  estimated_repeat_ratio: number
  facts_confirmed: string[]
  open_questions: string[]
  end_state: Record<string, unknown>
  warnings: string[]
  state_lock_violations: Array<Record<string, unknown>>
  latest_validation_report_id: string
}

export interface FusionPreviewDTO {
  estimated_words: number
  estimated_repeat_ratio: number
  expected_end_state: Record<string, unknown>
  expected_suspense_count: number
  risk_warnings: string[]
}

export interface FusionJobDTO {
  fusion_job_id: string
  chapter_id: string
  status: 'queued' | 'running' | 'completed' | 'warning' | 'failed'
  error_message: string
  fusion_draft: FusionDraftDTO | null
  preview: FusionPreviewDTO | null
}

export const chapterFusionApi = {
  createFusionJob: (chapterId: string, data: CreateFusionJobRequest) =>
    apiClient.post<FusionJobDTO>(`/chapters/${chapterId}/fusion-jobs`, data) as Promise<FusionJobDTO>,

  getLatestFusionJob: (chapterId: string) =>
    apiClient.get<FusionJobDTO>(`/chapters/${chapterId}/fusion-jobs/latest`) as Promise<FusionJobDTO>,

  getFusionJob: (fusionJobId: string) =>
    apiClient.get<FusionJobDTO>(`/fusion-jobs/${fusionJobId}`) as Promise<FusionJobDTO>,
}
