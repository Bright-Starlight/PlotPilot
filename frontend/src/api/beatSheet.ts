import { apiClient } from './config'

export interface BeatSheetSceneDTO {
  title: string
  goal: string
  pov_character: string
  location: string | null
  tone: string | null
  estimated_words: number
  order_index: number
}

export interface BeatSheetDTO {
  id: string
  chapter_id: string
  scenes: BeatSheetSceneDTO[]
  total_scenes: number
  total_estimated_words: number
}

export interface GenerateBeatSheetRequest {
  chapter_id: string
  outline: string
}

export const beatSheetApi = {
  getBeatSheet: (chapterId: string) =>
    apiClient.get<BeatSheetDTO>(`/beat-sheets/${chapterId}`) as Promise<BeatSheetDTO>,

  generateBeatSheet: (data: GenerateBeatSheetRequest) =>
    apiClient.post<BeatSheetDTO>('/beat-sheets/generate', data) as Promise<BeatSheetDTO>,

  deleteBeatSheet: (chapterId: string) =>
    apiClient.delete<{ success: boolean; message: string }>(`/beat-sheets/${chapterId}`) as Promise<{ success: boolean; message: string }>,
}
