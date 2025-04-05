export const config = {
    supabase: {
        url: process.env.SUPABASE_URL || '',
        anonKey: process.env.SUPABASE_ANON_KEY || '',
        storageBooksBucket: 'book-images',
        storageCoversBucket: 'book-covers',
    },
    llm: {
        model: process.env.LLM_MODEL || 'gpt-4o',
        temperature: 0.7,
    },
};