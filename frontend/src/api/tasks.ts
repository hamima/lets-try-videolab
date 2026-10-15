import axios from 'axios'

const http = axios.create({ baseURL: '/tasks' })

// ─── Types ────────────────────────────────────────────────────────────────────

export interface RunSummary {
  domain: string
  run_id: string
  workspace: string
  created_at: string | null
  active: boolean
  active_step: string | null
  steps_completed: number
  steps_failed: number
  steps_total: number
  videos: string[]
}

export interface StepDetail {
  id: string
  name: string
  type: string
  status: 'pending' | 'running' | 'done' | 'failed'
}

export interface RunStatus {
  run_id: string
  domain: string
  voice_id: string | null
  workspace: string
  active: boolean
  active_step: string | null
  steps: StepDetail[]
}

export interface AssetField {
  label: string
  content: string
}

export interface AssetItem {
  id: string
  fields: AssetField[]
}

export interface AssetScene {
  id: number
  assets: AssetItem[]
}

export interface ResearchSection {
  label: string
  content: string
}

export interface SceneBeat {
  narration: string
  duration: string
  visual: string
  purpose: string
  emotion: string
}

export interface Scene {
  id: number
  beats: SceneBeat[]
}

export interface AssetFile {
  type: 'image' | 'text'
  label: string
  filename: string
  // image fields
  url?: string
  // text fields
  content?: string
}

export interface AssetFolderItem {
  id: string
  files: AssetFile[]
}

export interface AssetFolderScene {
  id: string
  assets: AssetFolderItem[]
}

export type StepContent =
  | { kind: 'markdown'; content: string | null }
  | { kind: 'text'; content: string | null }
  | { kind: 'json'; content: unknown }
  | { kind: 'asset_manifest'; scenes: AssetScene[] }
  | { kind: 'asset_acquisition'; scenes: AssetScene[] }
  | { kind: 'research'; sections: ResearchSection[] }
  | { kind: 'story'; sections: ResearchSection[] }
  | { kind: 'scene_plan'; scenes: Scene[] }
  | { kind: 'assets_viewer'; scenes: AssetFolderScene[] }
  | { kind: 'audio'; url: string | null }
  | { kind: 'video'; url: string | null }
  | { kind: 'image_list'; images: { path: string; url: string; label: string; scene_id: string; asset_id: string; filename: string }[] }
  | { kind: 'animation_list'; items: { path: string; text: string; label: string; scene_id: string; asset_id: string; image_url: string | null }[] }
  | {
      kind: 'video_list'
      videos: {
        scene_id: string
        asset_id: string
        label: string
        thumbnail_url: string | null
        prompt: string
        video_url: string | null
        status: 'done' | 'pending'
      }[]
    }
  | { kind: 'asset_list'; files: { path: string; name: string; folder: string }[] }

// ─── API functions ────────────────────────────────────────────────────────────

export async function listRuns(domain?: string): Promise<RunSummary[]> {
  const params = domain ? { domain } : {}
  const { data } = await http.get<RunSummary[]>('/runs', { params })
  return data
}

export interface VideoConfig {
  duration_min_minutes: number
  duration_max_minutes: number
  video_split_percent: number
}

export async function startRun(
  domain: string,
  fresh: boolean,
  previewOnly = false,
  videoConfig?: VideoConfig,
): Promise<{ run_id: string; domain: string }> {
  const { data } = await http.post('/runs', {
    domain,
    fresh,
    preview_only: previewOnly,
    video_config: videoConfig,
  })
  return data
}

export interface CostEstimate {
  min_cost: number
  max_cost: number
}

export async function estimateCost(
  durationMin: number,
  durationMax: number,
  videoSplitPercent: number,
): Promise<CostEstimate> {
  const { data } = await http.get<CostEstimate>('/estimate-cost', {
    params: { duration_min: durationMin, duration_max: durationMax, video_split: videoSplitPercent },
  })
  return data
}

export async function continueRun(domain: string, runId: string): Promise<void> {
  await http.post(`/runs/${domain}/${runId}/continue`)
}

export async function deleteRun(domain: string, runId: string): Promise<void> {
  await http.delete(`/runs/${domain}/${runId}`)
}

export async function updateStepContent(
  domain: string,
  runId: string,
  stepId: string,
  data: { content?: string; sections?: ResearchSection[]; scenes?: Scene[]; asset_scenes?: AssetScene[] },
): Promise<void> {
  await http.put(`/runs/${domain}/${runId}/steps/${stepId}/content`, data)
}

export async function getRunStatus(domain: string, runId: string): Promise<RunStatus> {
  const { data } = await http.get<RunStatus>(`/runs/${domain}/${runId}`)
  return data
}

export async function runStep(domain: string, runId: string, stepId: string, force = false): Promise<void> {
  await http.post(`/runs/${domain}/${runId}/steps/${stepId}`, { force })
}

export async function getStepContent(domain: string, runId: string, stepId: string): Promise<StepContent> {
  const { data } = await http.get<StepContent>(`/runs/${domain}/${runId}/steps/${stepId}/content`)
  return data
}

export async function saveAssetFiles(
  domain: string,
  runId: string,
  sceneId: string,
  assetId: string,
  files: { filename: string; content: string }[],
): Promise<void> {
  await http.put(`/runs/${domain}/${runId}/assets/${sceneId}/${assetId}`, { files })
}

export async function regenerateAssetImage(
  domain: string,
  runId: string,
  sceneId: string,
  assetId: string,
): Promise<{ url: string }> {
  const { data } = await http.post<{ url: string }>(
    `/runs/${domain}/${runId}/assets/${sceneId}/${assetId}/regenerate-image`,
  )
  return data
}

export async function animateAsset(
  domain: string,
  runId: string,
  sceneId: string,
  assetId: string,
): Promise<{ url: string }> {
  const { data } = await http.post<{ url: string }>(
    `/runs/${domain}/${runId}/assets/${sceneId}/${assetId}/animate`,
  )
  return data
}

export async function uploadAssetImage(
  domain: string,
  runId: string,
  sceneId: string,
  assetId: string,
  file: File,
): Promise<{ url: string }> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<{ url: string }>(
    `/runs/${domain}/${runId}/assets/${sceneId}/${assetId}/image`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  return data
}

export interface SettingsField {
  key: string
  label: string
  secret: boolean
  type?: 'bool' | 'string'
}

export interface Settings {
  fields: SettingsField[]
  values: Record<string, string | boolean>
}

export async function getSettings(): Promise<Settings> {
  const { data } = await http.get<Settings>('/settings')
  return data
}

export async function updateSettings(settings: Record<string, string | boolean>): Promise<void> {
  await http.put('/settings', { settings })
}

export function fileUrl(filePath: string): string {
  // filePath is relative to workspace, e.g. "assets/scene_1/asset_1/image.png"
  // The /tasks/files/ endpoint is already in the URL returned by the backend
  return filePath
}
