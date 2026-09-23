import axios from 'axios'

const http = axios.create({ baseURL: '/api' })

export interface GenerateResponse {
  job_id: string
  num_frames: number
  fps: number
  duration_seconds: number
  width: number
  height: number
  seed: number | null
}

export interface StatusResponse {
  job_id: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  error: string | null
}

export async function generate(
  prompt: string,
  image: File,
  options?: {
    durationSeconds?: number
    width?: number
    height?: number
    seed?: number
    negativePrompt?: string
  }
): Promise<GenerateResponse> {
  const form = new FormData()
  form.append('prompt', prompt)
  form.append('image', image)
  if (options?.durationSeconds != null) form.append('duration_seconds', String(options.durationSeconds))
  if (options?.width != null) form.append('width', String(options.width))
  if (options?.height != null) form.append('height', String(options.height))
  if (options?.seed != null) form.append('seed', String(options.seed))
  if (options?.negativePrompt != null) form.append('negative_prompt', options.negativePrompt)

  const { data } = await http.post<GenerateResponse>('/generate', form)
  return data
}

export async function getStatus(jobId: string): Promise<StatusResponse> {
  const { data } = await http.get<StatusResponse>(`/status/${jobId}`)
  return data
}

export function getDownloadUrl(jobId: string): string {
  return `/api/download/${jobId}`
}
