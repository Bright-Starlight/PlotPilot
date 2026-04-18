import { apiClient } from './config'

export interface ValidationSpanDTO {
  paragraph_index: number
  start_offset: number
  end_offset: number
  excerpt: string
}

export interface ValidationIssueDTO {
  issue_id: string
  report_id: string
  chapter_id: string
  severity: 'P0' | 'P1' | 'P2'
  code: string
  title: string
  message: string
  spans: ValidationSpanDTO[]
  blocking: boolean
  suggest_patch: boolean
  status: string
  metadata: Record<string, unknown>
}

export interface ValidationTokenUsageDTO {
  input_tokens: number
  output_tokens: number
  total_tokens: number
}

export interface ValidationReportSummaryDTO {
  report_id: string
  chapter_id: string
  draft_type: string
  draft_id: string
  plan_version: number
  state_lock_version: number
  status: string
  passed: boolean
  blocking_issue_count: number
  p0_count: number
  p1_count: number
  p2_count: number
  token_usage: ValidationTokenUsageDTO
}

export interface ValidationReportDetailDTO extends ValidationReportSummaryDTO {
  issues_by_severity: Record<string, ValidationIssueDTO[]>
}

export interface StartValidationRequest {
  draft_type: 'fusion' | 'merged'
  draft_id: string
  plan_version?: number
  state_lock_version?: number
}

export interface PublishGateDTO extends ValidationReportDetailDTO {
  publishable: boolean
  blocking_issues: ValidationIssueDTO[]
}

export interface ValidationRepairPatchDTO {
  issue_id: string
  patch_text: string
  source: string
}

export const validationReportsApi = {
  startValidation: (chapterId: string, data: StartValidationRequest) =>
    apiClient.post<ValidationReportSummaryDTO>(`/chapters/${chapterId}/validate`, data) as Promise<ValidationReportSummaryDTO>,

  getValidationReport: (reportId: string) =>
    apiClient.get<ValidationReportDetailDTO>(`/validation-reports/${reportId}`) as Promise<ValidationReportDetailDTO>,

  getLatestValidationReport: (chapterId: string, params?: { draftType?: 'fusion' | 'merged'; draftId?: string }) => {
    const query = new URLSearchParams()
    if (params?.draftType) query.set('draft_type', params.draftType)
    if (params?.draftId) query.set('draft_id', params.draftId)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return apiClient.get<ValidationReportDetailDTO>(`/chapters/${chapterId}/validation-reports/latest${suffix}`) as Promise<ValidationReportDetailDTO>
  },

  listValidationIssues: (params?: { novelId?: string; chapterId?: string; severity?: string; status?: string }) => {
    const query = new URLSearchParams()
    if (params?.novelId) query.set('novel_id', params.novelId)
    if (params?.chapterId) query.set('chapter_id', params.chapterId)
    if (params?.severity) query.set('severity', params.severity)
    if (params?.status) query.set('status', params.status)
    const suffix = query.toString() ? `?${query.toString()}` : ''
    return apiClient.get<ValidationIssueDTO[]>(`/validation-issues${suffix}`) as Promise<ValidationIssueDTO[]>
  },

  updateValidationIssue: (issueId: string, status: 'unresolved' | 'resolved' | 'ignored') =>
    apiClient.patch<ValidationIssueDTO>(`/validation-issues/${issueId}`, { status }) as Promise<ValidationIssueDTO>,

  buildRepairPatch: (issueId: string) =>
    apiClient.post<ValidationRepairPatchDTO>(`/validation-issues/${issueId}/repair-patch`, {}) as Promise<ValidationRepairPatchDTO>,

  checkPublishable: (chapterId: string) =>
    apiClient.post<PublishGateDTO>(`/chapters/${chapterId}/publish-check`, {}) as Promise<PublishGateDTO>,
}
