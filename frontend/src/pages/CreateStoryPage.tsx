import { createSignal } from "solid-js";
import { useNavigate } from "@solidjs/router";
import { bookService } from "../services/api";
import type { CreateBookParams } from "../types/book";
import "../magical-glow.css";

export default function CreateStoryPage() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = createSignal(false);
  const [formData, setFormData] = createSignal<CreateBookParams>({
    characters: [],
    storyPrompt: "",
    ageRange: "4-5",
    numOfPages: undefined
  });
  const [charactersInput, setCharactersInput] = createSignal("");
  const [autofillLoading, setAutofillLoading] = createSignal(false);
  const [autofillError, setAutofillError] = createSignal<string | null>(null);
  const [creationMode, setCreationMode] = createSignal<'manual' | 'ai'>('manual');

  const handleCharactersBlur = () => {
    setFormData({
      ...formData(),
      characters: charactersInput().split(',').map(c => c.trim()).filter(Boolean)
    });
  };

  // Unified submit handler for both flows
  const handleSubmit = async (e: Event) => {
    e.preventDefault();
    // Always split characters input for manual mode
    const dataToSend = {
      ...formData(),
      characters: creationMode() === 'manual'
        ? charactersInput().split(',').map(c => c.trim()).filter(Boolean)
        : formData().characters, // AI flow: use whatever is in state (may be empty)
    };
    setIsLoading(true);
    try {
      const result = await bookService.createBook(dataToSend);
      if ((result as any).bookId || (result as any).book?.id) {
        const bookId = (result as any).bookId || (result as any).book?.id;
        navigate(`/book/${bookId}`);
      } else {
        console.error('No bookId returned from API:', result);
      }
    } catch (error) {
      console.error('Failed to create story:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleModeChange = (mode: 'manual' | 'ai') => {
    setCreationMode(mode);
    setAutofillError(null);
    setAutofillLoading(false);
  };

  // AI autofill handler: now just POST to /books with minimal fields and update UI with returned storyPrompt/characters
  const handleAIAutofill = async (e: Event) => {
    e.preventDefault();
    setAutofillError(null);
    if (!formData().ageRange) {
      setAutofillError('Please select an age range first!');
      return;
    }
    setAutofillLoading(true);
    try {
      // POST to /books with only ageRange and numOfPages
      const result = await bookService.createBook({
        ageRange: formData().ageRange,
        numOfPages: formData().numOfPages,
        characters: [],
        storyPrompt: ''
      });
      // The backend will autofill and return the generated fields
      const book = (result as any).book || result;
      setFormData({
        ...formData(),
        storyPrompt: book.story_prompt || '',
        characters: book.characters || []
      });
      setCharactersInput((book.characters || []).join(', '));
    } catch (err: any) {
      setAutofillError('Could not generate story details. Try again!');
    } finally {
      setAutofillLoading(false);
    }
  };

  return (
      <div class="max-w-2xl mx-auto">
        <div class="flex gap-4 mb-8 justify-center">
          <button
            type="button"
            class={`flex-1 px-6 py-4 rounded-2xl font-comic text-xl shadow-md transition-transform duration-300 border-2 ${creationMode() === 'manual' ? 'bg-white border-kiddy-primary text-kiddy-primary scale-105' : 'bg-gray-100 border-gray-200 text-gray-400 hover:scale-105'}`}
            onClick={() => handleModeChange('manual')}
            aria-pressed={creationMode() === 'manual'}
          >
            <span class="text-2xl mr-2">✍️</span> I want to choose the story details
            <div class="text-xs mt-1 text-gray-500">Pick characters, adventure, and more</div>
          </button>
          <button
            type="button"
            class={`flex-1 px-6 py-4 rounded-2xl font-comic text-xl shadow-md transition-transform duration-300 border-2 ${creationMode() === 'ai' ? 'bg-white border-blue-400 text-blue-500 scale-105' : 'bg-gray-100 border-gray-200 text-gray-400 hover:scale-105'}`}
            onClick={() => handleModeChange('ai')}
            aria-pressed={creationMode() === 'ai'}
          >
            <span class="text-2xl mr-2">🤖✨</span> Let AI surprise me!
            <div class="text-xs mt-1 text-gray-500">Just pick age, AI does the rest</div>
          </button>
        </div>
        <form onSubmit={handleSubmit} class="space-y-8 bg-gradient-to-br from-yellow-100 via-pink-100 to-blue-100 p-8 rounded-3xl shadow-2xl border-4 border-kiddy-primary/10">
          <div>
            <label class="block text-kiddy-primary text-lg mb-2 font-comic" for="ageRange">
              🎂 Age Range
            </label>
            <select
              id="ageRange"
              class="w-full p-3 border-2 border-kiddy-primary/30 rounded-xl focus:ring-2 focus:ring-kiddy-primary text-lg font-rounded bg-white"
              value={formData().ageRange}
              onChange={(e) => setFormData({
                ...formData(),
                ageRange: e.currentTarget.value
              })}
            >
              <option value="1-2">1-2 years</option>
              <option value="2-3">2-3 years</option>
              <option value="4-5">4-5 years</option>
              <option value="5-6">5-6 years</option>
              <option value="7-8">7-8 years</option>
            </select>
          </div>
          <div>
            <label class="block text-kiddy-primary text-lg mb-2 font-comic" for="numOfPages">
              Number of Pages (optional)
            </label>
            <input
              id="numOfPages"
              type="number"
              min="1"
              class="w-full p-3 border-2 border-kiddy-primary/30 rounded-xl focus:ring-2 focus:ring-kiddy-primary text-lg font-rounded bg-white"
              value={formData().numOfPages === undefined ? '' : formData().numOfPages}
              onInput={e => setFormData({ ...formData(), numOfPages: e.currentTarget.value ? Number(e.currentTarget.value) : undefined })}
              placeholder="e.g. 10"
            />
          </div>
          {creationMode() === 'manual' && (
            <>
              <div>
                <label class="block text-kiddy-primary text-lg mb-2 font-comic" for="characters">
                  🦄 Who are the characters in your story?
                </label>
                <input
                  id="characters"
                  type="text"
                  class="w-full p-3 border-2 border-kiddy-primary/30 rounded-xl focus:ring-2 focus:ring-kiddy-primary text-lg font-rounded bg-white"
                  placeholder="E.g. brave dragon, wise owl, silly robot"
                  value={charactersInput()}
                  onInput={(e) => setCharactersInput(e.currentTarget.value)}
                  onBlur={handleCharactersBlur}
                  autocomplete="off"
                />
                <p class="text-xs text-gray-500 mt-1 ml-1">Separate characters with commas. Be creative!</p>
              </div>
              <div>
                <label class="block text-kiddy-primary text-lg mb-2 font-comic" for="storyPrompt">
                  🌈 What is the story about? <span class="text-sm text-gray-500">(Describe your adventure! The more detail, the better!)</span>
                </label>
                <textarea
                  id="storyPrompt"
                  rows={5}
                  class="w-full p-3 border-2 border-kiddy-primary/30 rounded-xl focus:ring-2 focus:ring-kiddy-primary text-lg font-rounded bg-white resize-y min-h-[120px]"
                  placeholder="E.g. A magical journey through the forest to find a lost friend. Include details, twists, or anything special!"
                  value={formData().storyPrompt}
                  onInput={(e) => setFormData({
                    ...formData(),
                    storyPrompt: e.currentTarget.value
                  })}
                />
              </div>
              <button
                type="submit"
                class="w-full bg-gradient-to-r from-kiddy-primary to-kiddy-secondary text-white font-comic text-xl py-4 rounded-full shadow-lg hover:scale-105 transition-transform duration-300 disabled:opacity-50 mt-6 flex items-center justify-center gap-2"
                disabled={isLoading()}
              >
                {isLoading() ? (
                  <>
                    <span class="animate-spin mr-2">🌀</span> Creating Story...
                  </>
                ) : (
                  <>
                    <span>🚀</span> Create My Story!
                  </>
                )}
              </button>
            </>
          )}
          {creationMode() === 'ai' && (
            <>
              <div class="flex flex-col gap-2 items-center mt-2 mb-4">
                <button
                  type="button"
                  class={`flex items-center gap-2 px-6 py-3 rounded-full font-comic text-lg shadow-lg transition-transform duration-300 bg-gradient-to-r from-blue-400 to-pink-400 text-white hover:scale-105 focus:ring-4 focus:ring-blue-200 ${autofillLoading() ? 'opacity-60 cursor-not-allowed' : ''}`}
                  onClick={handleAIAutofill}
                  disabled={autofillLoading()}
                  title="Let the AI pick the story idea and characters for you!"
                >
                  <span class="text-2xl">🤖✨</span>
                  {autofillLoading() ? 'Letting AI Choose...' : 'Let AI Choose For Me'}
                </button>
                {autofillError() && <span class="text-red-600 text-sm mt-1">{autofillError()}</span>}
                <span class="text-xs text-gray-500">(Only Age Range required. AI will do the rest!)</span>
              </div>
              {(formData().storyPrompt || (formData().characters && formData().characters.length > 0)) && (
                <div class="bg-white/80 rounded-2xl p-5 mt-4 shadow-lg border-2 border-blue-100">
                  <div class="mb-3">
                    <div class="font-comic text-lg text-blue-700 mb-1">✨ Story Prompt</div>
                    <textarea
                      class="w-full p-3 border-2 border-blue-200 rounded-xl focus:ring-2 focus:ring-blue-400 text-lg font-rounded bg-white resize-y min-h-[80px]"
                      value={formData().storyPrompt}
                      onInput={(e) => setFormData({ ...formData(), storyPrompt: e.currentTarget.value })}
                    />
                  </div>
                  <div class="mb-3">
                    <div class="font-comic text-lg text-blue-700 mb-1">🦄 Characters</div>
                    <input
                      type="text"
                      class="w-full p-3 border-2 border-blue-200 rounded-xl focus:ring-2 focus:ring-blue-400 text-lg font-rounded bg-white"
                      value={charactersInput()}
                      onInput={(e) => setCharactersInput(e.currentTarget.value)}
                      onBlur={handleCharactersBlur}
                    />
                    <p class="text-xs text-gray-500 mt-1 ml-1">Edit if you want! Separate with commas.</p>
                  </div>
                  <button
                    type="submit"
                    class="w-full bg-gradient-to-r from-blue-400 to-pink-400 text-white font-comic text-xl py-4 rounded-full shadow-lg hover:scale-105 transition-transform duration-300 disabled:opacity-50 mt-6 flex items-center justify-center gap-2"
                    disabled={isLoading()}
                  >
                    {isLoading() ? (
                      <>
                        <span class="animate-spin mr-2">🌀</span> Creating Story...
                      </>
                    ) : (
                      <>
                        <span>🚀</span> Create My Story!
                      </>
                    )}
                  </button>
                </div>
              )}
            </>
          )}
        </form>
      </div>
  );
}