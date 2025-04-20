import { createSignal } from "solid-js";
import { useNavigate } from "@solidjs/router";
import { bookService } from "../services/api";
import type { CreateBookParams } from "../types/book";

export default function CreateStoryPage() {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = createSignal(false);
  const [formData, setFormData] = createSignal<CreateBookParams>({
    characters: [],
    storyPrompt: "",
    ageRange: "4-5"
  });
  const [charactersInput, setCharactersInput] = createSignal("");

  const handleCharactersBlur = () => {
    setFormData({
      ...formData(),
      characters: charactersInput().split(',').map(c => c.trim()).filter(Boolean)
    });
  };

  const handleSubmit = async (e: Event) => {
    e.preventDefault();
    setFormData({
      ...formData(),
      characters: charactersInput().split(',').map(c => c.trim()).filter(Boolean)
    });
    setIsLoading(true);

    try {
      const result = await bookService.createBook(formData());
      if (result.bookId) {
        navigate(`/book/${result.bookId}`);
      } else {
        console.error('No bookId returned from API:', result);
      }
    } catch (error) {
      console.error('Failed to create story:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
      <div class="max-w-2xl mx-auto">
        {/* Home navigation button */}
        <div class="mb-6 flex justify-start">
          <a href="/" class="inline-flex items-center gap-2 bg-gradient-to-r from-kiddy-primary to-kiddy-secondary text-white font-comic px-5 py-3 rounded-full shadow-lg hover:scale-105 transition-transform duration-300">
            <span class="text-xl">🏠</span> <span>Back to Home</span>
          </a>
        </div>
        <h1 class="text-4xl font-comic text-center text-kiddy-primary mb-4 animate-bounce">
          ✨ Create Your Magical Story ✨
        </h1>
        <p class="text-center text-lg text-gray-600 mb-8 font-rounded">
          Unleash your imagination! Add fun characters, a wild adventure, and help us make a story just for you.
        </p>
        <form onSubmit={handleSubmit} class="space-y-8 bg-gradient-to-br from-yellow-100 via-pink-100 to-blue-100 p-8 rounded-3xl shadow-2xl border-4 border-kiddy-primary/10">
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
                autoComplete="off"
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
        </form>
      </div>
  );
}