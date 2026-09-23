import { useEffect, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { getSettings, updateSettings, type SettingsField } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

function SecretInput({
  value,
  onChange,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="relative">
      <Input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="pr-10 font-mono text-sm"
        autoComplete="off"
      />
      <button
        type="button"
        onClick={() => setVisible(v => !v)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
        tabIndex={-1}
      >
        {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
      </button>
    </div>
  )
}

export default function SettingsPage() {
  const [fields, setFields]   = useState<SettingsField[]>([])
  const [values, setValues]   = useState<Record<string, string | boolean>>({})
  const [dirty, setDirty]     = useState(false)
  const [saving, setSaving]   = useState(false)
  const [saved, setSaved]     = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    getSettings()
      .then(data => {
        setFields(data.fields)
        setValues(data.values)
      })
      .catch(() => setError('Could not load settings. Is the backend running?'))
      .finally(() => setLoading(false))
  }, [])

  function handleChange(key: string, value: string | boolean) {
    setValues(prev => ({ ...prev, [key]: value }))
    setDirty(true)
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await updateSettings(values)
      setDirty(false)
      setSaved(true)
    } catch {
      setError('Failed to save settings.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="max-w-xl mx-auto px-4 py-12">
        <p className="text-sm text-muted-foreground">Loading settings…</p>
      </div>
    )
  }

  const mockActive = values['MOCK_AI'] === true

  return (
    <div className="max-w-xl mx-auto px-4 py-10">
      <h1 className="text-lg font-semibold mb-1">Settings</h1>
      <p className="text-sm text-muted-foreground mb-8">
        API keys and service configuration. Values are saved to{' '}
        <code className="text-xs bg-muted px-1 py-0.5 rounded">settings.json</code> in the project root.
      </p>

      {mockActive && (
        <div className="mb-6 flex items-center gap-2 rounded-md border border-amber-400 bg-amber-50 px-4 py-3 text-amber-800 dark:border-amber-500 dark:bg-amber-950 dark:text-amber-300">
          <span className="text-base">⚠</span>
          <span className="text-sm font-medium">
            AI Mock Mode is ON — all AI calls return placeholder outputs. Disable before production use.
          </span>
        </div>
      )}

      {error && (
        <p className="text-sm text-destructive mb-6">{error}</p>
      )}

      <div className="space-y-6">
        {fields.map(field => (
          <div key={field.key} className="space-y-1.5">
            <Label htmlFor={field.key} className="text-sm font-medium">
              {field.label}
            </Label>
            {field.type === 'bool' ? (
              <div className="flex items-center gap-3">
                <button
                  id={field.key}
                  type="button"
                  role="switch"
                  aria-checked={values[field.key] === true}
                  onClick={() => handleChange(field.key, values[field.key] !== true)}
                  className={[
                    'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    values[field.key] === true
                      ? 'bg-amber-500'
                      : 'bg-input',
                  ].join(' ')}
                >
                  <span
                    className={[
                      'inline-block h-4 w-4 rounded-full bg-white shadow transition-transform',
                      values[field.key] === true ? 'translate-x-6' : 'translate-x-1',
                    ].join(' ')}
                  />
                </button>
                <span className="text-sm text-muted-foreground">
                  {values[field.key] === true ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            ) : field.secret ? (
              <SecretInput
                value={(values[field.key] as string) ?? ''}
                onChange={v => handleChange(field.key, v)}
                placeholder={`Enter ${field.label}`}
              />
            ) : (
              <Input
                id={field.key}
                value={(values[field.key] as string) ?? ''}
                onChange={e => handleChange(field.key, e.target.value)}
                placeholder={`Enter ${field.label}`}
                className="font-mono text-sm"
              />
            )}
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3 mt-8">
        <Button disabled={!dirty || saving} onClick={handleSave}>
          {saving ? 'Saving…' : 'Save settings'}
        </Button>
        {saved && !dirty && (
          <span className="text-sm text-emerald-600">Settings saved</span>
        )}
      </div>
    </div>
  )
}
