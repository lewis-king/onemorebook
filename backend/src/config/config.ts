export const config = {
    supabase: {
        url: process.env.SUPABASE_URL || '',
        anonKey: process.env.SUPABASE_ANON_KEY || '',
        storageBooksBucket: 'book-imgs',
        storageCoversBucket: 'book-imgs',
    },
    llm: {
        model: process.env.LLM_MODEL || 'gpt-4.1',
        temperature: 0.7,
    },
};