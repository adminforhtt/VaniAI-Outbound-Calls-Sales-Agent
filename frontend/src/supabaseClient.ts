import { createClient } from '@supabase/supabase-js';

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL || 'https://nqgjtartntbyhipafjjf.supabase.co';
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY || 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5xZ2p0YXJ0bnRieWhpcGFmampmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUyMDM2MDEsImV4cCI6MjA5MDc3OTYwMX0.DVsmcoBnYKnDs5513kqYMzk-zsiewz6ri06WzDigsaA';

export const supabase = createClient(supabaseUrl, supabaseAnonKey);
