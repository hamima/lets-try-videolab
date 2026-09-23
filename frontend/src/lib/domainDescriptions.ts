export interface DomainDescription {
  role: string
  task: string
}

export const DOMAIN_DESCRIPTIONS: Record<string, DomainDescription> = {
  political: {
    role: 'Senior investigative journalist.',
    task: 'Finds political stories with hidden motivations, real consequences, and stakeholder conflict.',
  },
  science: {
    role: 'Senior science journalist.',
    task: 'Uncovers discoveries and breakthroughs that are surprising, counterintuitive, and accessible to everyone.',
  },
  business: {
    role: 'Senior business and financial journalist.',
    task: 'Tracks corporate scandals, market disruptions, and power struggles where billions are at stake.',
  },
  history: {
    role: 'Senior historical journalist.',
    task: 'Resurfaces forgotten or misunderstood stories with a clear lesson for today.',
  },
  sports: {
    role: 'Senior sports journalist.',
    task: 'Goes beyond the scoreline — human drama, systemic issues, and cultural shifts in sport.',
  },
  technology: {
    role: 'Senior technology journalist.',
    task: 'Investigates innovations and controversies reshaping society, explained for a non-technical audience.',
  },
  general_knowledge: {
    role: 'Senior investigative journalist.',
    task: 'Hunts for surprising, counterintuitive stories with universal appeal that challenge everyday assumptions.',
  },
  general: {
    role: 'Senior investigative journalist.',
    task: 'Researches any given topic to find the most compelling angle for a documentary audience.',
  },
}
