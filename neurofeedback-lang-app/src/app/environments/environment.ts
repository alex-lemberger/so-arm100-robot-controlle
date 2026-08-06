export const environment = {
  production: false,
  useMockData: true,
  device: 'mock' as 'mock' | 'neurosity' | 'muse',
  engagementTier: 'standard' as 'standard' | 'premium',
  wordpressApiUrl: 'https://your-wordpress-site.com/wp-json/wp/v2/posts',
  neurosityDeviceId: 'YOUR_DEVICE_ID',
  simWsUrl: 'ws://localhost:8765', // Default local URL
  pipelineApiUrl: 'http://localhost:8000',
  pipelineSimWsUrl: 'ws://localhost:8000/sim', // used by sub-project D
  supabase: {
    url: 'https://hmiwxefpxbvjstsdywxb.supabase.co',
    anonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhtaXd4ZWZweGJ2anN0c2R5d3hiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA3ODY0NTksImV4cCI6MjA5NjM2MjQ1OX0.COhFY0HVtUKU3lFd8PBpF5sLckD4jZS1qPpbVTwzJ6M',
  },
  shopId: 'pilot-shop-01',
  collections: {
    metrics: 'metrics',
    sessions: 'sessions',
    correlation: 'correlation',
    exercises: 'exercises',
  },
};